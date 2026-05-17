import json
import traceback
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, OuterRef, Subquery
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.models import User

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.api_core import exceptions as google_exceptions

from app.models import (
    AIProvider, APIModel, Conversation, Message, UserProfile, Course, CourseEnrollment
)

# --- Chatbot API Management ---
@login_required
def chatbot_api_management(request):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('dashboard')
    
    providers = AIProvider.objects.all().prefetch_related('api_models')
    context = {
        'providers': providers,
        'page_title': 'Quản lý API Chatbot'
    }
    return render(request, 'chat/chatbot_api_management.html', context)

@login_required
def chatbot_api_form(request, id=None):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    if id:
        provider = get_object_or_404(AIProvider.objects.prefetch_related('api_models'), id=id)
        page_title = f'Sửa nhà cung cấp: {provider.name}'
    else:
        provider = None
        page_title = 'Thêm nhà cung cấp API'

    if request.method == 'POST':
        if 'save_provider' in request.POST:
            name = request.POST.get('name')
            api_key = request.POST.get('api_key')

            if not name or not api_key:
                messages.error(request, 'Tên và API Key không được để trống.')
                return render(request, 'chat/chatbot_api_form.html', {'provider': provider, 'page_title': page_title})

            if provider:
                provider.name = name
                provider.api_key = api_key
                provider.save()
                messages.success(request, f'Đã cập nhật nhà cung cấp "{name}" thành công.')
                return redirect('chatbot_api_management')
            else:
                if AIProvider.objects.filter(name=name).exists():
                    messages.error(request, f'Nhà cung cấp với tên "{name}" đã tồn tại.')
                    return render(request, 'chat/chatbot_api_form.html', {'page_title': page_title})
                
                new_provider = AIProvider.objects.create(name=name, api_key=api_key)
                messages.success(request, f'Đã thêm nhà cung cấp "{name}" thành công.')
                return redirect('edit_chatbot_api', id=new_provider.id)

        elif 'add_model' in request.POST:
            if not provider:
                 messages.error(request, 'Không tìm thấy nhà cung cấp để thêm model.')
                 return redirect('chatbot_api_management')

            model_name = request.POST.get('model_name')
            if model_name:
                APIModel.objects.create(provider=provider, model_name=model_name)
                messages.success(request, f'Đã thêm model "{model_name}" vào nhà cung cấp "{provider.name}".')
            else:
                messages.error(request, 'Tên model không được để trống.')
            
            return redirect('edit_chatbot_api', id=provider.id)

    context = {
        'provider': provider,
        'page_title': page_title
    }
    return render(request, 'chat/chatbot_api_form.html', context)

@login_required
@require_POST
def delete_chatbot_api(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')
    
    provider = get_object_or_404(AIProvider, id=id)
    name = provider.name
    provider.delete()
    messages.success(request, f'Đã xóa nhà cung cấp "{name}" thành công.')
    return redirect('chatbot_api_management')

@login_required
@require_POST
def set_active_provider(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('chatbot_api_management')

    AIProvider.objects.update(is_active=False)
    provider = get_object_or_404(AIProvider, id=id)
    provider.is_active = True
    provider.save()
    messages.success(request, f'Đã kích hoạt nhà cung cấp "{provider.name}".')
    return redirect('chatbot_api_management')

@login_required
@require_POST
def set_active_api_model(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('chatbot_api_management')

    model = get_object_or_404(APIModel, id=id)
    APIModel.objects.filter(provider=model.provider).update(is_active=False)
    model.is_active = True
    model.save()
    messages.success(request, f'Đã kích hoạt model "{model.model_name}" cho nhà cung cấp "{model.provider.name}".')
    return redirect('edit_chatbot_api', id=model.provider.id)

@login_required
@require_POST
def delete_api_model(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    model = get_object_or_404(APIModel, id=id)
    provider_id = model.provider.id
    model_name = model.model_name
    
    if model.is_active:
        messages.error(request, f'Không thể xóa model "{model_name}" đang hoạt động.')
    else:
        model.delete()
        messages.success(request, f'Đã xóa model "{model_name}" thành công.')

    return redirect('edit_chatbot_api', id=provider_id)


# --- Live Chat Support Views ---

@login_required
def inbox_view(request):
    if not (request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)):
        messages.error(request, "Bạn không có quyền truy cập trang này.")
        return redirect('home')

    latest_message = Message.objects.filter(conversation=OuterRef('pk')).order_by('-timestamp')

    # Managers see unassigned conversations and conversations assigned to them
    conversations = Conversation.objects.filter(
        Q(assignee__isnull=True) | Q(assignee=request.user)
    ).annotate(
        latest_message_content=Subquery(latest_message.values('content')[:1]),
        latest_message_time=Subquery(latest_message.values('timestamp')[:1]),
        unread_count=Count('messages', filter=Q(messages__is_read=False) & ~Q(messages__sender=request.user))
    ).order_by('-latest_message_time')

    return render(request, 'chat/inbox.html', {'conversations': conversations})

@login_required
def conversation_detail_view(request, conversation_id):
    is_support_staff = request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)

    if not is_support_staff:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        # Staff can only access conversations that are assigned to them or are unassigned
        conversation = get_object_or_404(Conversation, Q(id=conversation_id) & (Q(assignee=request.user) | Q(assignee__isnull=True)))
        # If the conversation was unassigned, assign it to the current staff member upon viewing
        if conversation.assignee is None:
            conversation.assignee = request.user
            conversation.save()

    conversation.messages.filter(~Q(sender=request.user), is_read=False).update(is_read=True)

    messages_list = conversation.messages.all().order_by('timestamp')
    
    return render(request, 'chat/conversation_detail.html', {
        'conversation': conversation,
        'messages_list': messages_list,
        'is_support_staff': is_support_staff
    })

@login_required
def get_conversation_messages(request, conversation_id):
    is_support_staff = request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)

    if not is_support_staff:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        conversation = get_object_or_404(Conversation, id=conversation_id, assignee=request.user)

    last_message_id = request.GET.get('last_message_id')
    query = conversation.messages.select_related('sender', 'sender__userprofile')

    if last_message_id and last_message_id.isdigit():
        query = query.filter(id__gt=int(last_message_id))

    new_messages = query.order_by('timestamp')
    
    messages_data = [
        {
            'id': msg.id,
            'sender': {
                'id': msg.sender.id,
                'username': msg.sender.username,
                'avatar_url': msg.sender.userprofile.avatar.url if hasattr(msg.sender, 'userprofile') and msg.sender.userprofile.avatar else None,
            },
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%H:%M')
        }
        for msg in new_messages
    ]

    for msg in new_messages:
        if msg.sender != request.user:
            msg.is_read = True
            msg.save(update_fields=['is_read'])
            
    return JsonResponse({'messages': messages_data})

@login_required
@csrf_exempt
@require_POST
def start_conversation_api(request):
    content = request.POST.get('content')
    if not content:
        return JsonResponse({'status': 'error', 'message': 'Nội dung tin nhắn không được để trống.'}, status=400)

    conversation, created = Conversation.objects.get_or_create(user=request.user)
    
    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content
    )
    
    return JsonResponse({
        'status': 'success',
        'message': 'Tin nhắn đã được gửi.',
        'conversation_id': conversation.id
    })

@login_required
@csrf_exempt
@require_POST
def send_reply_api(request, conversation_id):
    is_support_staff = request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)

    if not is_support_staff:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        conversation = get_object_or_404(Conversation, id=conversation_id, assignee=request.user)

    content = request.POST.get('content')
    if not content:
        return JsonResponse({'status': 'error', 'message': 'Nội dung không được để trống.'}, status=400)

    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content
    )
    
    return JsonResponse({
        'status': 'success',
        'message': {
            'id': message.id,
            'sender': {
                'id': message.sender.id,
                'username': message.sender.username,
                'avatar_url': message.sender.userprofile.avatar.url if hasattr(message.sender, 'userprofile') and message.sender.userprofile.avatar else None
            },
            'content': message.content,
            'timestamp': message.timestamp.strftime('%H:%M')
        }
    })

@login_required
@require_POST
def assign_conversation_api(request, conversation_id):
    if not (request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)):
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền thực hiện hành động này.'}, status=403)
    
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if conversation.assignee is None:
        conversation.assignee = request.user
        conversation.save()
        return JsonResponse({'status': 'success', 'message': f'Cuộc trò chuyện đã được gán cho {request.user.username}'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Cuộc trò chuyện này đã được gán cho người khác.'}, status=400)

@login_required
@require_POST
def delete_conversation_api(request, conversation_id):
    if not (request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)):
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền thực hiện hành động này.'}, status=403)

    conversation = get_object_or_404(Conversation, id=conversation_id)
    if conversation.assignee == request.user:
        conversation.delete()
        return JsonResponse({'status': 'success', 'message': 'Cuộc trò chuyện đã được xóa.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Bạn chỉ có thể xóa các cuộc trò chuyện được gán cho bạn.'}, status=403)

@login_required
def get_user_conversation_api(request):
    """Checks if a conversation exists for the current user and returns its ID."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User not authenticated'}, status=401)

    try:
        conversation = Conversation.objects.get(user=request.user)
        return JsonResponse({'conversation_id': conversation.id})
    except Conversation.DoesNotExist:
        return JsonResponse({})

@login_required
def check_unread_api(request):
    if request.user.is_staff or getattr(request.user, 'userprofile', {}).is_manager:
        unread_count = Message.objects.filter(
            Q(conversation__assignee=request.user) | Q(conversation__assignee__isnull=True),
            is_read=False
        ).exclude(sender=request.user).count()
    else:
        unread_count = Message.objects.filter(
            conversation__user=request.user, 
            is_read=False
        ).exclude(sender=request.user).count()
            
    return JsonResponse({'unread_count': unread_count})


@csrf_exempt
@require_http_methods(["POST"])
def clear_chat_history(request):
    """Clears the user's chatbot history."""
    try:
        if not request.session.session_key:
            request.session.create()

        data = json.loads(request.body)
        user_id = data.get('user_id')
        
        if user_id:
            history_key = f'gemini_chat_history_user_{user_id}'
        else:
            history_key = f'gemini_chat_history_session_{request.session.session_key}'

        cache.delete(history_key)
        
        initial_message = "Xin chào! Tôi là Trợ lý ảo của Ngôn Ngữ Ký Hiệu. Tôi có thể giúp gì cho bạn?"
        
        return JsonResponse({"status": "success", "message": "Lịch sử trò chuyện đã được xoá.", "initial_message": initial_message})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt
def gemini_chat(request):
    if request.method == 'POST':
        try:
            if not request.session.session_key:
                request.session.create()

            data = json.loads(request.body)
            user_id = data.get('user_id')
            user_message = data.get('message')

            if user_id:
                history_key = f'gemini_chat_history_user_{user_id}'
            else:
                history_key = f'gemini_chat_history_session_{request.session.session_key}'

            if not user_message:
                return JsonResponse({'error': 'No message provided'}, status=400)

            api_key = settings.GEMINI_API_KEY
            if not api_key:
                return JsonResponse({'error': 'Gemini API key not configured'}, status=500)

            genai.configure(api_key=api_key)

            # --- Tool Helper Functions ---
            def get_courses_list():
                """Gets a list of all available course titles."""
                try:
                    courses = Course.objects.all().values_list('title', flat=True)
                    if not courses:
                        return json.dumps({"status": "error", "message": "Hiện tại không có khóa học nào."})
                    return json.dumps({"status": "success", "courses": list(courses)})
                except Exception as e:
                    return json.dumps({"status": "error", "message": f"Lỗi khi truy vấn khóa học: {str(e)}"})

            def enroll_in_course(course_name: str):
                """Enrolls the logged-in user in a specific course by its name."""
                if not user_id:
                    return json.dumps({"status": "error", "message": "Bạn cần đăng nhập để ghi danh."})
                try:
                    user = User.objects.get(pk=user_id)
                    user_profile = UserProfile.objects.get(user=user)
                    course_to_enroll = Course.objects.get(title__iexact=course_name)

                    enrollment, created = CourseEnrollment.objects.get_or_create(
                        user_profile=user_profile, 
                        course=course_to_enroll
                    )

                    if created:
                        return json.dumps({"status": "success", "message": f"Bạn đã ghi danh thành công vào khóa học '{course_name}'."})
                    else:
                        return json.dumps({"status": "info", "message": f"Bạn đã ghi danh vào khóa học '{course_name}' từ trước rồi."})
                except (User.DoesNotExist, UserProfile.DoesNotExist):
                     return json.dumps({"status": "error", "message": "Không tìm thấy thông tin người dùng."})
                except Course.DoesNotExist:
                    return json.dumps({"status": "error", "message": f"Không tìm thấy khóa học với tên '{course_name}'."})
                except Exception as e:
                    return json.dumps({"status": "error", "message": f"Đã có lỗi xảy ra: {str(e)}"})

            def navigate_to_page(page_name: str):
                """
                Returns a JSON object with a URL for the frontend to navigate to.
                """
                try:
                    page_map = {
                        'cộng đồng': 'blog_feed',
                        'blog': 'blog_feed',
                        'feed': 'blog_feed',
                        'dự đoán ai': 'predict_symbol',
                        'dự đoán': 'predict_symbol',
                        'ai': 'predict_symbol',
                        'thư viện': 'symbol_library',
                        'library': 'symbol_library',
                    }
                    normalized_page_name = page_name.lower().strip()
                    
                    if normalized_page_name in page_map:
                        url = reverse(page_map[normalized_page_name])
                        return {'status': 'success', 'action': 'navigate', 'url': url}
                    else:
                        return {'status': 'error', 'message': f"Tôi không tìm thấy trang nào có tên là '{page_name}'. Các trang có sẵn: Cộng đồng, Dự đoán AI, Thư viện."}
                except Exception as e:
                    return {'status': 'error', 'message': f"Đã xảy ra lỗi khi tìm trang: {str(e)}"}

            # --- Function & Tool Definitions ---
            available_functions = {
                "get_courses_list": get_courses_list,
                "enroll_in_course": enroll_in_course,
                "navigate_to_page": navigate_to_page,
            }
            
            tools = [
                genai.protos.Tool(function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name='get_courses_list',
                        description="Lấy danh sách tất cả các tiêu đề khóa học có sẵn.",
                        parameters=genai.protos.Schema()
                    ),
                    genai.protos.FunctionDeclaration(
                        name='enroll_in_course',
                        description="Ghi danh người dùng đã đăng nhập vào một khóa học cụ thể theo tên.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                'course_name': genai.protos.Schema(type=genai.protos.Type.STRING)
                            },
                            required=['course_name']
                        )
                    ),
                    genai.protos.FunctionDeclaration(
                        name='navigate_to_page',
                        description="Điều hướng người dùng đến một trang cụ thể. Chỉ sử dụng cho các trang: 'Cộng đồng', 'Dự đoán AI', và 'Thư viện'.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                'page_name': genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Tên của trang, ví dụ: 'Cộng đồng', 'Dự đoán AI', 'Thư viện'"
                                )
                            },
                            required=['page_name']
                        )
                    )
                ])
            ]
            
            model = genai.GenerativeModel(
                'gemini-2.0-flash-exp',
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                },
                tools=tools
            )

            history = cache.get(history_key)

            if history is None:
                system_prompt = """
Bạn là 'Trợ lý ảo' của trang web 'Ngôn Ngữ Ký Hiệu'.
Nhiệm vụ của bạn là giúp người dùng bằng cách gọi các hàm (tools) được cung cấp.
Luôn trả lời bằng tiếng Việt.

QUY TẮC:
1.  **SỬ DỤNG HÀM**: Nhiệm vụ chính của bạn là gọi hàm.
    -   Nếu người dùng muốn đến các trang 'Cộng đồng', 'Dự đoán AI', hoặc 'Thư viện', hãy gọi hàm `navigate_to_page`.
    -   Nếu người dùng muốn xem các khóa học, hãy gọi `get_courses_list`.
    -   Nếu người dùng muốn đăng ký một khóa học, hãy gọi `enroll_in_course`.
2.  **LÀM RÕ**: Nếu không chắc chắn, hãy hỏi lại. Ví dụ: "Bạn muốn đăng ký khóa học nào?".
3.  **TRẢ LỜI TỪ KẾT QUẢ**: Dựa vào kết quả hàm trả về để tạo câu trả lời tự nhiên cho người dùng. Nếu hàm báo lỗi, hãy thông báo lỗi đó.
4.  **GIỚI HẠN**: Nếu câu hỏi không liên quan đến chức năng của trang web, hãy lịch sự từ chối: "Xin lỗi, tôi chỉ có thể giúp về các tính năng của trang web này."
5.  **VĂN BẢN THUẦN TÚY**: Không dùng Markdown (không có *, #, v.v.).

Bắt đầu cuộc trò chuyện.
"""
                history = [
                    {'role': 'user', 'parts': [system_prompt]},
                    {'role': 'model', 'parts': ["Xin chào! Tôi là Trợ lý ảo của Ngôn Ngữ Ký Hiệu. Tôi có thể giúp gì cho bạn?"]}
                ]

            chat_session = model.start_chat(history=history)
            response = chat_session.send_message(user_message)

            while response.candidates and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
                function_call = response.candidates[0].content.parts[0].function_call
                function_name = function_call.name

                if function_name not in available_functions:
                    function_response_content = json.dumps({"status": "error", "message": "Chức năng không được hỗ trợ."})
                else:
                    function_to_call = available_functions[function_name]
                    function_args = {key: value for key, value in function_call.args.items()}
                    
                    result = function_to_call(**function_args)

                    if function_name == 'navigate_to_page' and result.get('action') == 'navigate' and result.get('status') == 'success':
                        return JsonResponse(result)
                    else:
                        function_response_content = json.dumps(result) if isinstance(result, dict) else result

                response = chat_session.send_message(
                    genai.protos.Part(function_response=genai.protos.FunctionResponse(
                        name=function_name,
                        response={'content': function_response_content}
                    ))
                )

            final_reply = response.text.replace('*', '')

            history_for_cache = [type(m).to_dict(m) for m in chat_session.history]
            cache.set(history_key, history_for_cache, timeout=3600)

            return JsonResponse({'reply': final_reply})
        except google_exceptions.ResourceExhausted:
            return JsonResponse({'reply': 'Rất tiếc, hệ thống đang tạm thời quá tải do vượt quá giới hạn yêu cầu. Vui lòng thử lại sau ít phút.'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)

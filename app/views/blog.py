from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Exists, OuterRef
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from app.models import Post, Comment, Like
from app.forms import PostForm, CommentForm

@login_required(login_url='login')
def blog_feed(request):
    post_form = PostForm()
    comment_form = CommentForm()

    # Annotate posts with like count and whether the current user has liked it
    user_liked = Like.objects.filter(post=OuterRef('pk',), user=request.user)
    posts = Post.objects.all() \
        .select_related('author__userprofile') \
        .prefetch_related('comments__author__userprofile') \
        .annotate(like_count=Count('likes', distinct=True), user_has_liked=Exists(user_liked)) \
        .order_by('-created_at')

    context = {
        'posts': posts,
        'post_form': post_form,
        'comment_form': comment_form,
    }
    return render(request, 'blog/blog_feed.html', context)

@login_required(login_url='login')
@require_POST
def create_post(request):
    form = PostForm(request.POST, request.FILES)
    if form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        messages.success(request, 'Đã đăng bài thành công!')
    else:
        messages.error(request, 'Đã có lỗi xảy ra. Vui lòng thử lại.')
    return redirect('blog_feed')

@login_required(login_url='login')
@require_POST
def add_comment_to_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        
        # Prepare the comment data to be sent back as JSON
        comment_data = {
            'id': comment.id,
            'author': {
                'username': comment.author.username,
                'avatar': comment.author.userprofile.avatar.url if comment.author.userprofile.avatar else None,
            },
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
            'content': comment.content,
        }
        return JsonResponse({'status': 'ok', 'comment': comment_data})
    else:
        return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)


@login_required(login_url='login')
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    
    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    post.refresh_from_db()

    return JsonResponse({'status': 'ok', 'liked': liked, 'like_count': post.likes.count()})

@login_required(login_url='login')
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author == request.user or request.user.is_staff:
        post.delete()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền xoá bài đăng này.'}, status=403)

@login_required(login_url='login')
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author == request.user or request.user.is_staff:
        comment.delete()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền xoá bình luận này.'}, status=403)

@login_required(login_url='login')
def get_post_details(request, post_id):
    """
    Returns the like count and comment count for a given post.
    """
    post = get_object_or_404(Post, id=post_id)
    user_liked = Like.objects.filter(post=post, user=request.user).exists()
    
    comments = post.comments.select_related('author__userprofile').order_by('created_at')
    
    comments_data = [{
        'id': c.id,
        'author': {
            'username': c.author.username,
            'avatar_url': c.author.userprofile.avatar.url if c.author.userprofile.avatar else None
        },
        'content': c.content,
        'created_at': c.created_at.strftime('%b. %d, %Y, %I:%M %p')
    } for c in comments]

    data = {
        'like_count': post.likes.count(),
        'user_has_liked': user_liked,
        'comments': comments_data,
        'comment_count': post.comments.count(),
    }
    return JsonResponse(data)

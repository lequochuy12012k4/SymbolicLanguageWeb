from django.urls import path, reverse_lazy
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),

    # Password Reset URLs
    path('password_reset/', views.password_reset_request, name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete')
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html'
    ), name='password_reset_complete'),

    # Student-facing URLs
    path('progress/', views.progress_view, name='progress'),
    path('courses/', views.course_list, name='course_list'),
    path('course/<int:id>/', views.course_detail, name='course_detail'),
    path('chapter/<int:chapter_id>/exercises/', views.chapter_exercises, name='chapter_exercises'),
    path('exercise/<int:exercise_id>/', views.exercise_detail, name='exercise_detail'),
    path('course/enroll/<int:id>/', views.enroll_course, name='enroll_course'),
    path('course/review/<int:id>/', views.review_course, name='review_course'),
    path('predict-symbol/', views.predict_symbol, name='predict_symbol'),

    # Admin-facing URLs
    path('dashboard/', views.dashboard, name='dashboard'),
    path('course/add/', views.add_course, name='add_course'),
    path('course/edit/<int:id>/', views.edit_course, name='edit_course'),
    path('course/delete/<int:id>/', views.delete_course, name='delete_course'),
    path('course-management/', views.course_management, name='course_management'),
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_add, name='user_add'),
    path('users/edit/<int:id>/', views.user_edit, name='user_edit'),
    path('users/delete/<int:id>/', views.user_delete, name='user_delete'),

    # Chapter and Exercise Management
    path('course/<int:course_id>/chapter/add/', views.add_chapter, name='add_chapter'),
    path('chapter/<int:chapter_id>/edit/', views.edit_chapter, name='edit_chapter'),
    path('chapter/<int:chapter_id>/delete/', views.delete_chapter, name='delete_chapter'),
    path('chapter/<int:chapter_id>/exercise/add/', views.add_exercise, name='add_exercise'),
    path('exercise/<int:exercise_id>/edit/', views.edit_exercise, name='edit_exercise'),
    path('exercise/<int:exercise_id>/delete/', views.delete_exercise, name='delete_exercise'),

    # AI Model Management
    path('model-management/', views.model_management, name='model_management'),
    path('model/add/', views.model_form, name='add_model'),
    path('model/edit/<int:id>/', views.model_form, name='edit_model'),
    path('model/delete/<int:id>/', views.delete_model, name='delete_model'),
    path('model/set-active/<int:id>/', views.set_active_model, name='set_active_model'),

    # Chatbot API Management
    path('chatbot-api-management/', views.chatbot_api_management, name='chatbot_api_management'),
    path('chatbot-api/add/', views.chatbot_api_form, name='add_chatbot_api'),
    path('chatbot-api/edit/<int:id>/', views.chatbot_api_form, name='edit_chatbot_api'),
    path('chatbot-api/delete/<int:id>/', views.delete_chatbot_api, name='delete_chatbot_api'),
    path('chatbot-api/set-active-provider/<int:id>/', views.set_active_provider, name='set_active_provider'),
    path('chatbot-api/set-active-model/<int:id>/', views.set_active_api_model, name='set_active_api_model'),
    path('chatbot-api/model/delete/<int:id>/', views.delete_api_model, name='delete_api_model'),

    # Blog URLs
    path('blog/', views.blog_feed, name='blog_feed'),
    path('blog/post/', views.create_post, name='create_post'),
    path('blog/post/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    path('blog/post/<int:post_id>/comment/', views.add_comment_to_post, name='add_comment_to_post'),
    path('blog/comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    path('blog/post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('blog/post/<int:post_id>/details/', views.get_post_details, name='get_post_details'),

    # Symbol Library URLs
    path('library/manage/', views.symbol_library_management, name='symbol_library_management'),
    path('library/category/add/', views.add_symbol_category, name='add_symbol_category'),
    path('library/category/<int:category_id>/edit/', views.edit_symbol_category, name='edit_symbol_category'),
    path('library/category/<int:category_id>/delete/', views.delete_symbol_category, name='delete_symbol_category'),
    path('library/category/<int:category_id>/symbol/add/', views.add_symbol, name='add_symbol'),
    path('library/symbol/<int:symbol_id>/edit/', views.edit_symbol, name='edit_symbol'),
    path('library/symbol/<int:symbol_id>/delete/', views.delete_symbol, name='delete_symbol'),
    path('library/', views.symbol_library_view, name='symbol_library'),
    path('library/category/<slug:category_slug>/', views.symbol_category_detail_view, name='symbol_category_detail'),
    path('library/symbol/<slug:symbol_slug>/', views.symbol_detail_view, name='symbol_detail'),

    # Live Chat Support URLs
    path('inbox/', views.inbox_view, name='inbox'),
    path('conversation/<int:conversation_id>/', views.conversation_detail_view, name='conversation_detail'),
    path('api/start_conversation/', views.start_conversation_api, name='start_conversation_api'),
    path('api/send_reply/<int:conversation_id>/', views.send_reply_api, name='send_reply_api'),
    path('api/conversation/<int:conversation_id>/messages/', views.get_conversation_messages, name='get_conversation_messages'),
    path('api/check_unread/', views.check_unread_api, name='check_unread_api'),
    path('api/get_user_conversation/', views.get_user_conversation_api, name='get_user_conversation_api'),
    path('api/conversation/<int:conversation_id>/assign/', views.assign_conversation_api, name='assign_conversation_api'),
    path('api/conversation/<int:conversation_id>/delete/', views.delete_conversation_api, name='delete_conversation_api'),

    # Gemini Chatbot URLs
    path('gemini-chat/', views.gemini_chat, name='gemini_chat'),
    path('clear-chat-history/', views.clear_chat_history, name='clear_chat_history'),

    # Deprecated
    path('language/<int:id>/', views.language_detail, name='language_detail'),
    path('language/add/<int:id>/', views.add_language, name='add_language'),
]

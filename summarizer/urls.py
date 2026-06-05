from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('summarize/', views.summarize, name='summarize'),
    path('create-mcq/', views.create_mcq, name='create_mcq'),
    path('mcq/', views.mcq_practice_page, name='mcq'),
    path('mcq/generate/', views.generate_mcq_quiz, name='generate_mcq_quiz'),
    path('chatbot/', views.chatbot, name='chatbot'),
    path('history/', views.history, name='history'),
    path('history/delete/<int:pk>/', views.delete_summary, name='delete_summary'),
    path('history/view/<int:pk>/', views.view_summary, name='view_summary'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('forgot-password/', views.forgot_password_request, name='forgot_password'),
    path('forgot-password/verify/', views.forgot_password_verify, name='forgot_password_verify'),
    path('forgot-password/new-password/', views.forgot_password_set_new_password, name='forgot_password_set_new_password'),
]

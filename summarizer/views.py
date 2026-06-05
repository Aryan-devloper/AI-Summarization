import json
import importlib
import mimetypes
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    ForgotPasswordOTPForm,
    ForgotPasswordRequestForm,
    ProfileUpdateForm,
    RegisterForm,
    SetNewPasswordForm,
    SummarizeForm,
)
from .models import PasswordResetOTP, Summary, UserProfile
from .utils import extract_text_from_upload, generate_otp


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.mpeg', '.mpg', '.mov', '.avi', '.flv', '.webm', '.wmv', '.3gp'}
INLINE_MEDIA_LIMIT_BYTES = 20 * 1024 * 1024


def get_gemini_summary(text, summary_type, api_key):
    """Generate summary using Google Gemini API"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompts = {
            'short': f"Provide a very concise summary (2-3 sentences) of the following text:\n\n{text}",
            'medium': f"Provide a medium-length summary (1-2 paragraphs) of the following text, covering the main points:\n\n{text}",
            'detailed': f"Provide a comprehensive and detailed summary of the following text, covering all important aspects, arguments, and conclusions:\n\n{text}",
            'bullets': f"Summarize the following text as a bullet point list (use • for bullets). Each bullet should be a distinct key point:\n\n{text}",
            'keypoints': f"Extract and list the 5-7 most important key points from the following text. Format each as: KEY POINT N: [point]\n\n{text}",
        }

        prompt = prompts.get(summary_type, prompts['medium'])
        response = model.generate_content(prompt)
        return response.text, None
    except Exception as e:
        return None, str(e)


def _gemini_error_response(error_message):
    error_text = str(error_message)
    lowered = error_text.lower()

    is_rate_limited = (
        'quota exceeded' in lowered
        or 'rate limit' in lowered
        or '429' in lowered
        or 'resourceexhausted' in lowered
    )

    if is_rate_limited:
        retry_after = None
        retry_match = re.search(r'Please retry in ([0-9]+(?:\.[0-9]+)?)s', error_text)
        if retry_match:
            retry_after = int(round(float(retry_match.group(1))))
        else:
            delay_match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_text)
            if delay_match:
                retry_after = int(delay_match.group(1))

        message = 'The AI service is temporarily rate-limited or out of quota.'
        if retry_after:
            message += f' Please try again in about {retry_after} seconds.'
        else:
            message += ' Please try again later.'

        return message, 429

    return f'AI Error: {error_text}', 500


def _summary_prompt(summary_type, source_kind='text'):
    prompts = {
        'short': {
            'text': 'Provide a very concise summary (2-3 sentences) of the following text:',
            'image': 'Provide a very concise summary (2-3 sentences) of the following image, focusing on the main visible content and purpose:',
            'video': 'Provide a very concise summary (2-3 sentences) of the following video, focusing on the main events, spoken content, and key visual details:',
        },
        'medium': {
            'text': 'Provide a medium-length summary (1-2 paragraphs) of the following text, covering the main points:',
            'image': 'Provide a medium-length summary (1-2 paragraphs) of the following image, covering the main visible details, context, and notable elements:',
            'video': 'Provide a medium-length summary (1-2 paragraphs) of the following video, covering the main events, spoken content, and important visual details:',
        },
        'detailed': {
            'text': 'Provide a comprehensive and detailed summary of the following text, covering all important aspects, arguments, and conclusions:',
            'image': 'Provide a comprehensive and detailed summary of the following image, covering the scene, visible objects, context, and any readable text:',
            'video': 'Provide a comprehensive and detailed summary of the following video, covering the sequence of events, spoken content, visual details, and conclusions:',
        },
        'bullets': {
            'text': 'Summarize the following text as a bullet point list (use • for bullets). Each bullet should be a distinct key point:',
            'image': 'Summarize the following image as a bullet point list (use • for bullets). Each bullet should be a distinct visual observation or important detail:',
            'video': 'Summarize the following video as a bullet point list (use • for bullets). Each bullet should be a distinct key event, spoken point, or visual detail:',
        },
        'keypoints': {
            'text': 'Extract and list the 5-7 most important key points from the following text. Format each as: KEY POINT N: [point]',
            'image': 'Extract and list the 5-7 most important key points from the following image. Format each as: KEY POINT N: [point]',
            'video': 'Extract and list the 5-7 most important key points from the following video. Format each as: KEY POINT N: [point]',
        },
    }
    return prompts.get(summary_type, prompts['medium']).get(source_kind, prompts['medium']['text'])


def _uploaded_media_kind(uploaded_file):
    suffix = Path((uploaded_file.name or '').lower()).suffix
    if suffix in IMAGE_EXTENSIONS:
        return 'image'
    if suffix in VIDEO_EXTENSIONS:
        return 'video'
    return None


def _media_mime_type(uploaded_file):
    mime_type, _ = mimetypes.guess_type(uploaded_file.name or '')
    if mime_type:
        return mime_type

    suffix = Path((uploaded_file.name or '').lower()).suffix
    fallback_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.heic': 'image/heic',
        '.heif': 'image/heif',
        '.mp4': 'video/mp4',
        '.mpeg': 'video/mpeg',
        '.mpg': 'video/mpeg',
        '.mov': 'video/quicktime',
        '.avi': 'video/avi',
        '.flv': 'video/x-flv',
        '.webm': 'video/webm',
        '.wmv': 'video/wmv',
        '.3gp': 'video/3gpp',
    }
    return fallback_types.get(suffix, 'application/octet-stream')


def get_gemini_media_summary(uploaded_file, summary_type, api_key):
    try:
        genai_module_name = '.'.join(['google', 'genai'])
        types_module_name = '.'.join(['google', 'genai', 'types'])
        genai = importlib.import_module(genai_module_name)
        types = importlib.import_module(types_module_name)

        media_kind = _uploaded_media_kind(uploaded_file)
        if not media_kind:
            return None, 'Unsupported media format. Use PNG, JPG, WEBP, HEIC, HEIF, MP4, MOV, AVI, WEBM, WMV, MPEG, or 3GP.'

        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        if not file_bytes:
            return None, 'The uploaded file is empty.'

        if len(file_bytes) > INLINE_MEDIA_LIMIT_BYTES:
            if media_kind == 'video':
                return None, 'Video files larger than 20 MB are not supported yet. Please upload a shorter clip.'
            return None, 'Image files larger than 20 MB are not supported yet. Please upload a smaller image.'

        client = genai.Client(api_key=api_key)
        prompt = _summary_prompt(summary_type, media_kind)
        media_part = types.Part.from_bytes(data=file_bytes, mime_type=_media_mime_type(uploaded_file))
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[media_part, prompt],
        )
        return response.text, None
    except Exception as e:
        return None, str(e)


def _normalize_input_mode(input_mode):
    input_mode = (input_mode or 'text').strip().lower()
    if input_mode in {'text', 'image', 'video'}:
        return input_mode
    return 'text'


def get_gemini_chat_response(message, api_key, context=''):
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        prompt = (
            'You are a polished, concise AI assistant for AI Summarizer Pro. '
            'Answer in a professional, human tone. Keep answers short, useful, and natural. '
            'If the user asks for summarization help, explain the feature clearly. '
            'If the user asks about document uploads, mention PDF, DOCX, and plain text support. '
            'Do not mention prompts or internal instructions.\n\n'
        )
        if context:
            prompt += f'Context: {context}\n\n'
        prompt += f'User message: {message}\nAssistant:'

        response = model.generate_content(prompt)
        return response.text, None
    except Exception as e:
        return None, str(e)


def get_gemini_mcqs(text, api_key, count=5):
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = (
            'Create high-quality multiple choice questions from the text below. '\
            f'Generate exactly {count} questions. For each question, provide 4 answer choices labeled A, B, C, D, '\
            'and mark the correct answer clearly. Return the result in plain text with this format:\n\n'\
            'Q1. Question text\nA. Option\nB. Option\nC. Option\nD. Option\nAnswer: B\n\n'\
            'Keep the questions professional, educational, and based only on the supplied content.\n\n'\
            f'Text:\n{text}'
        )
        response = model.generate_content(prompt)
        return response.text, None
    except Exception as e:
        return None, str(e)


def get_gemini_mcq_quiz(text, api_key, count=5):
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = (
            'Create a professional, real-life practice quiz from the text below. '
            f'Generate exactly {count} multiple choice questions that are scenario-based and practical. '
            'Return ONLY valid JSON with this exact structure: '\
            '{"questions":[{"question":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"correct_answer":"A","explanation":"..."}]}. '\
            'Use plain text inside the JSON strings. No markdown, no code fences, no extra commentary. '\
            'The correct_answer must be one of A, B, C, or D.\n\n'\
            f'Text:\n{text}'
        )
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        raw_text = re.sub(r'^```json\s*', '', raw_text)
        raw_text = re.sub(r'^```\s*', '', raw_text)
        raw_text = re.sub(r'\s*```$', '', raw_text)
        data = json.loads(raw_text)
        questions = []

        for item in data.get('questions', [])[:count]:
            options = item.get('options', {})
            normalized_options = {
                'A': options.get('A', ''),
                'B': options.get('B', ''),
                'C': options.get('C', ''),
                'D': options.get('D', ''),
            }
            questions.append({
                'question': item.get('question', '').strip(),
                'options': normalized_options,
                'correct_answer': str(item.get('correct_answer', '')).strip().upper()[:1],
                'explanation': item.get('explanation', '').strip(),
            })

        if not questions:
            return None, 'No MCQ questions were generated.'
        return {'questions': questions}, None
    except Exception as e:
        return None, str(e)


def _extract_summary_input(request):
    if request.FILES.get('document'):
        uploaded_file = request.FILES['document']
        extracted_text, error = extract_text_from_upload(uploaded_file)
        if error:
            return None, None, error
        title = Path(uploaded_file.name).stem.replace('_', ' ').replace('-', ' ').strip().title()
        return extracted_text, title, None

    text = request.POST.get('text', '').strip()
    if not text and request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return None, None, 'Invalid JSON'
        text = data.get('text', '').strip()

    title = text.split('.')[0][:80] if text else ''
    return text, title, None


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to AI Summarizer Pro, {user.username}!')
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(request.GET.get('next', 'dashboard'))
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def dashboard(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    total_summaries = Summary.objects.filter(user=user).count()
    last_7_days = timezone.now() - timedelta(days=7)
    recent_count = Summary.objects.filter(user=user, created_at__gte=last_7_days).count()
    recent_summaries = Summary.objects.filter(user=user)[:5]

    type_counts = Summary.objects.filter(user=user).values('summary_type').annotate(count=Count('id'))
    type_data = {item['summary_type']: item['count'] for item in type_counts}

    # Weekly activity
    daily_counts = []
    for i in range(6, -1, -1):
        day = timezone.now() - timedelta(days=i)
        count = Summary.objects.filter(
            user=user,
            created_at__date=day.date()
        ).count()
        daily_counts.append({'day': day.strftime('%a'), 'count': count})

    total_words_saved = 0
    for s in Summary.objects.filter(user=user):
        total_words_saved += max(0, s.word_count_original - s.word_count_summary)

    context = {
        'profile': profile,
        'total_summaries': total_summaries,
        'recent_count': recent_count,
        'recent_summaries': recent_summaries,
        'type_data': json.dumps(type_data),
        'daily_counts': json.dumps(daily_counts),
        'total_words_saved': total_words_saved,
    }
    return render(request, 'dashboard.html', context)


@login_required
def summarize(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        summary_type = request.POST.get('summary_type', 'short')
        input_mode = _normalize_input_mode(request.POST.get('input_mode'))
        uploaded_file = request.FILES.get('document')
        media_kind = _uploaded_media_kind(uploaded_file) if uploaded_file else None

        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            text = data.get('text', '').strip()
            summary_type = data.get('summary_type', summary_type)
            input_mode = _normalize_input_mode(data.get('input_mode', input_mode))
            title = text.split('.')[0][:80] if text else ''
        elif uploaded_file and media_kind:
            text = ''
            title = Path(uploaded_file.name).stem.replace('_', ' ').replace('-', ' ').strip().title()
        else:
            text, title, error = _extract_summary_input(request)
            if error:
                return JsonResponse({'error': error}, status=400)

        if input_mode in {'image', 'video'}:
            if not uploaded_file:
                return JsonResponse({'error': f'{input_mode.title()} mode requires an uploaded {input_mode} file.'}, status=400)
            if media_kind != input_mode:
                return JsonResponse({'error': f'Please upload a valid {input_mode} file for {input_mode} mode.'}, status=400)

        api_key = settings.GEMINI_API_KEY
        if api_key == 'YOUR_GEMINI_API_KEY_HERE':
            return JsonResponse({'error': 'Gemini API key not configured. Please set GEMINI_API_KEY in settings.py or environment variable.'}, status=400)

        if uploaded_file and media_kind:
            summary_text, error = get_gemini_media_summary(uploaded_file, summary_type, api_key)
            source_text = f'Uploaded {media_kind}: {uploaded_file.name}'
        else:
            if len(text) < 50:
                return JsonResponse({'error': 'Text must be at least 50 characters long.'}, status=400)
            summary_text, error = get_gemini_summary(text, summary_type, api_key)
            source_text = text

        if error:
            message, status_code = _gemini_error_response(error)
            return JsonResponse({'error': message}, status=status_code)

        word_count_original = len(source_text.split()) if source_text else 0
        word_count_summary = len(summary_text.split())
        if not title:
            if uploaded_file and media_kind:
                title = Path(uploaded_file.name).stem.replace('_', ' ').replace('-', ' ').strip().title()
            else:
                title = text.split('.')[0][:80] if text else 'Untitled Summary'

        summary_obj = Summary.objects.create(
            user=request.user,
            original_text=source_text,
            summary=summary_text,
            summary_type=summary_type,
            title=title,
            word_count_original=word_count_original,
            word_count_summary=word_count_summary,
        )

        return JsonResponse({
            'success': True,
            'summary': summary_text,
            'summary_id': summary_obj.id,
            'word_count_original': word_count_original,
            'word_count_summary': word_count_summary,
            'compression_ratio': summary_obj.compression_ratio(),
            'summary_type': summary_type,
            'title': title,
        })

    from .models import SUMMARY_TYPES
    return render(request, 'summarizer/summarize.html', {'profile': profile, 'types': SUMMARY_TYPES})


@login_required
@require_POST
def create_mcq(request):
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            text = data.get('text', '').strip()
        else:
            text, _, error = _extract_summary_input(request)
            if error:
                return JsonResponse({'error': error}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if len(text) < 50:
        return JsonResponse({'error': 'Text must be at least 50 characters long.'}, status=400)

    api_key = settings.GEMINI_API_KEY
    if api_key == 'YOUR_GEMINI_API_KEY_HERE' or not api_key:
        return JsonResponse({'error': 'Gemini API key not configured.'}, status=400)

    mcq_text, error = get_gemini_mcqs(text, api_key)
    if error:
        message, status_code = _gemini_error_response(error)
        return JsonResponse({'error': message}, status=status_code)

    return JsonResponse({'success': True, 'mcqs': mcq_text})


@login_required
def mcq_practice_page(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'summarizer/mcq.html', {'profile': profile})


@login_required
@require_POST
def generate_mcq_quiz(request):
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            text = data.get('text', '').strip()
        else:
            text, _, error = _extract_summary_input(request)
            if error:
                return JsonResponse({'error': error}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if len(text) < 50:
        return JsonResponse({'error': 'Text must be at least 50 characters long.'}, status=400)

    api_key = settings.GEMINI_API_KEY
    if api_key == 'YOUR_GEMINI_API_KEY_HERE':
        return JsonResponse({'error': 'Gemini API key not configured.'}, status=400)

    quiz, error = get_gemini_mcq_quiz(text, api_key)
    if error:
        message, status_code = _gemini_error_response(error)
        return JsonResponse({'error': message}, status=status_code)

    return JsonResponse({'success': True, 'quiz': quiz})


@login_required
@require_POST
def chatbot(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    message = data.get('message', '').strip()
    context = data.get('context', '').strip()
    if not message:
        return JsonResponse({'error': 'Message is required.'}, status=400)

    api_key = settings.GEMINI_API_KEY
    if api_key == 'YOUR_GEMINI_API_KEY_HERE':
        return JsonResponse({'error': 'Gemini API key not configured.'}, status=400)

    reply, error = get_gemini_chat_response(message, api_key, context)
    if error:
        message, status_code = _gemini_error_response(error)
        return JsonResponse({'error': message}, status=status_code)

    return JsonResponse({'success': True, 'reply': reply})


@login_required
def history(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    query = request.GET.get('q', '')
    summary_type_filter = request.GET.get('type', '')

    summaries = Summary.objects.filter(user=request.user)

    if query:
        summaries = summaries.filter(
            Q(title__icontains=query) |
            Q(original_text__icontains=query) |
            Q(summary__icontains=query)
        )

    if summary_type_filter:
        summaries = summaries.filter(summary_type=summary_type_filter)

    paginator = Paginator(summaries, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'profile': profile,
        'page_obj': page_obj,
        'query': query,
        'summary_type_filter': summary_type_filter,
        'total_count': summaries.count(),
    }
    return render(request, 'summarizer/history.html', context)


@login_required
def delete_summary(request, pk):
    summary = get_object_or_404(Summary, pk=pk, user=request.user)
    if request.method == 'POST':
        summary.delete()
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True})
        messages.success(request, 'Summary deleted successfully.')
        return redirect('history')
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def view_summary(request, pk):
    summary = get_object_or_404(Summary, pk=pk, user=request.user)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'summarizer/view_summary.html', {'summary': summary, 'profile': profile})


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=profile, user=request.user)

    total_summaries = Summary.objects.filter(user=request.user).count()
    context = {'profile': profile, 'form': form, 'total_summaries': total_summaries}
    return render(request, 'summarizer/profile.html', context)


@login_required
def change_password(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'summarizer/change_password.html', {'form': form, 'profile': profile})


def forgot_password_request(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ForgotPasswordRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            user = User.objects.filter(email__iexact=email).first()

            request.session['reset_email'] = email

            if user:
                otp = generate_otp()
                expires_at = timezone.now() + timedelta(minutes=10)
                PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)
                otp_record = PasswordResetOTP.objects.create(
                    user=user,
                    email=email,
                    otp=otp,
                    expires_at=expires_at,
                )

                # Always print to the terminal console for easy retrieval during testing
                print("\n" + "=" * 50)
                print(f"DEBUG PASSWORD RESET OTP (ALWAYS LOGGED):\nTarget Email: {email}\nGenerated Code: {otp}")
                print("=" * 50 + "\n")

                try:
                    send_mail(
                        subject='Your AI Summarizer Pro verification code',
                        message=(
                            f'Use this code to reset your password: {otp}\n\n'
                            'This code expires in 10 minutes. If you did not request it, ignore this email.'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[email],
                        fail_silently=False,
                    )
                except Exception as mail_err:
                    messages.warning(request, f"Local test warning: Email sending failed. The OTP has been printed to the Django terminal log: {otp}")

                request.session['reset_user_id'] = user.id
                request.session['reset_otp_id'] = otp_record.id
            else:
                request.session.pop('reset_user_id', None)
                request.session.pop('reset_otp_id', None)

            messages.info(request, 'If the email exists, a verification code has been sent.')
            return redirect('forgot_password_verify')
    else:
        form = ForgotPasswordRequestForm()

    return render(request, 'registration/forgot_password.html', {'form': form})


def forgot_password_verify(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    reset_email = request.session.get('reset_email')
    if not reset_email:
        return redirect('forgot_password')

    if request.method == 'POST':
        form = ForgotPasswordOTPForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp'].strip()
            reset_user_id = request.session.get('reset_user_id')

            if reset_user_id:
                otp_record = PasswordResetOTP.objects.filter(
                    user_id=reset_user_id,
                    otp=otp,
                    is_used=False,
                ).order_by('-created_at').first()

                if otp_record and otp_record.is_valid():
                    otp_record.is_used = True
                    otp_record.save(update_fields=['is_used'])
                    request.session['otp_verified_reset_user_id'] = reset_user_id
                    return redirect('forgot_password_set_new_password')

            messages.error(request, 'The code is invalid or has expired.')
    else:
        form = ForgotPasswordOTPForm()

    return render(request, 'registration/verify_otp.html', {'form': form, 'email': reset_email})


def forgot_password_set_new_password(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    reset_user_id = request.session.get('otp_verified_reset_user_id')
    if not reset_user_id:
        return redirect('forgot_password')

    user = get_object_or_404(User, pk=reset_user_id)

    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['new_password1']
            user.set_password(password)
            user.save(update_fields=['password'])

            PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)
            for key in ('reset_user_id', 'reset_otp_id', 'reset_email', 'otp_verified_reset_user_id'):
                request.session.pop(key, None)

            messages.success(request, 'Your password has been updated successfully. You can sign in now.')
            return redirect('login')
    else:
        form = SetNewPasswordForm()

    return render(request, 'registration/set_new_password.html', {'form': form, 'email': request.session.get('reset_email', '')})


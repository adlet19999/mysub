import logging
import re
from uuid import uuid4

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PartnerProfile


logger = logging.getLogger(__name__)

PHONE_RU_RE = re.compile(r"^\+7\d{10}$")


def normalize_ru_phone(raw_phone: str) -> str:
	cleaned = re.sub(r"[\s\-()]", "", raw_phone or "")
	return cleaned


class HealthView(APIView):
	def get(self, request):
		return Response({"ok": True, "service": "django-backend"})


class AuthRegisterView(APIView):
	def post(self, request):
		full_name = (request.data.get("full_name") or "").strip()
		phone = normalize_ru_phone((request.data.get("phone") or "").strip())
		email = (request.data.get("email") or "").strip().lower()
		password = request.data.get("password") or ""
		user_type = ((request.data.get("user_type") or "partner").strip().lower())
		company_name = (request.data.get("company_name") or "").strip()
		address = (request.data.get("address") or "").strip()
		business_category = (request.data.get("business_category") or "").strip()

		if not full_name or not phone or not email or not password:
			return Response({"message": "full_name, phone, email, password обязательны"}, status=400)

		if not PHONE_RU_RE.match(phone):
			return Response({"message": "Телефон должен быть в формате +7XXXXXXXXXX"}, status=400)

		if User.objects.filter(username=email).exists():
			return Response({"message": "Пользователь уже существует"}, status=409)

		user = User.objects.create_user(
			username=email,
			email=email,
			password=password,
			first_name=full_name,
		)
		PartnerProfile.objects.create(
			user=user,
			phone=phone,
			user_type=user_type,
			company_name=company_name,
			address=address,
			business_category=business_category,
		)

		return Response(
			{
				"ok": True,
				"user": {
					"id": user.id,
					"username": user.username,
					"email": user.email,
					"phone": phone,
					"user_type": user_type,
					"company_name": company_name,
					"address": address,
					"business_category": business_category,
				},
			},
			status=status.HTTP_201_CREATED,
		)


class AuthLoginView(APIView):
	def post(self, request):
		username = (request.data.get("username") or "").strip().lower()
		password = request.data.get("password") or ""

		if not username or not password:
			return Response({"message": "username и password обязательны"}, status=400)

		user = authenticate(request, username=username, password=password)
		if user is None:
			inactive_user = (
				User.objects.filter(username__iexact=username, is_active=False).first()
				or User.objects.filter(email__iexact=username, is_active=False).first()
			)
			if inactive_user and inactive_user.check_password(password):
				from partner_api.models import Manager

				is_archived_manager = Manager.objects.filter(email__iexact=inactive_user.email, is_active=False).exists()
				if is_archived_manager:
					return Response({"message": "Аккаунт менеджера заблокирован"}, status=403)
			return Response({"message": "Неверный логин или пароль"}, status=401)

		profile = getattr(user, "partner_profile", None)
		user_type = profile.user_type if profile else "partner"
		must_change_password = profile.must_change_password if profile else False
		if user_type == "manager":
			from partner_api.models import Manager

			is_archived = Manager.objects.filter(email__iexact=user.email, is_active=False).exists()
			if is_archived:
				return Response({"message": "Аккаунт менеджера заблокирован"}, status=403)
		phone = profile.phone if profile else "+7"
		company_name = profile.company_name if profile else ""
		address = profile.address if profile else ""
		business_category = profile.business_category if profile else ""

		return Response(
			{
				"ok": True,
				"access": f"access_{uuid4().hex}",
				"refresh": f"refresh_{uuid4().hex}",
				"user": {
					"id": user.id,
					"username": user.username,
					"email": user.email,
					"phone": phone,
					"user_type": user_type,
					"must_change_password": must_change_password,
					"company_name": company_name,
					"address": address,
					"business_category": business_category,
				},
			}
		)


class AuthForgotPasswordView(APIView):
	def post(self, request):
		email = (request.data.get("email") or "").strip().lower()
		if not email:
			return Response({"message": "Email обязателен"}, status=status.HTTP_400_BAD_REQUEST)

		user = User.objects.filter(email__iexact=email, is_active=True).first()
		if user:
			uid = urlsafe_base64_encode(force_bytes(user.pk))
			token = default_token_generator.make_token(user)
			reset_url = f"{settings.FRONTEND_PARTNER_BASE_URL.rstrip('/')}/partner/reset-password?uid={uid}&token={token}"
			try:
				send_mail(
					subject="Сброс пароля MySub",
					message=(
						"Чтобы задать новый пароль, перейдите по ссылке:\n\n"
						f"{reset_url}\n\n"
						"Если вы не запрашивали сброс пароля, проигнорируйте это письмо."
					),
					from_email=settings.DEFAULT_FROM_EMAIL,
					recipient_list=[user.email],
					fail_silently=False,
				)
			except Exception:
				# ответ не должен раскрывать, существует ли аккаунт, даже если SMTP недоступен
				logger.exception("Не удалось отправить письмо сброса пароля")

		return Response({"message": "Если аккаунт существует, письмо уже отправлено"})


class AuthResetPasswordView(APIView):
	def post(self, request):
		uid = (request.data.get("uid") or "").strip()
		token = (request.data.get("token") or "").strip()
		new_password = request.data.get("new_password") or ""

		if not uid or not token or not new_password:
			return Response({"message": "uid, token и новый пароль обязательны"}, status=status.HTTP_400_BAD_REQUEST)

		try:
			user_id = force_str(urlsafe_base64_decode(uid))
			user = User.objects.get(pk=user_id, is_active=True)
		except (User.DoesNotExist, ValueError, TypeError, OverflowError):
			return Response({"message": "Ссылка сброса недействительна или устарела"}, status=status.HTTP_400_BAD_REQUEST)

		if not default_token_generator.check_token(user, token):
			return Response({"message": "Ссылка сброса недействительна или устарела"}, status=status.HTTP_400_BAD_REQUEST)

		try:
			validate_password(new_password, user)
		except ValidationError as error:
			return Response({"message": " ".join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

		user.set_password(new_password)
		user.save(update_fields=["password"])
		return Response({"message": "Пароль обновлен"})


class AuthInitialPasswordChangeView(APIView):
	def post(self, request):
		email = (request.data.get("email") or "").strip().lower()
		current_password = request.data.get("current_password") or ""
		new_password = request.data.get("new_password") or ""
		user = authenticate(request, username=email, password=current_password)
		if user is None:
			return Response({"message": "Неверный текущий пароль"}, status=status.HTTP_400_BAD_REQUEST)

		profile = getattr(user, "partner_profile", None)
		if not profile or not profile.must_change_password:
			return Response({"message": "Смена пароля не требуется"}, status=status.HTTP_400_BAD_REQUEST)

		try:
			validate_password(new_password, user)
		except ValidationError as error:
			return Response({"message": " ".join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

		user.set_password(new_password)
		user.save(update_fields=["password"])
		profile.must_change_password = False
		profile.save(update_fields=["must_change_password"])
		return Response({"message": "Пароль обновлен"})

# Create your views here.

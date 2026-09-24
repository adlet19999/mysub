import logging
import re
from datetime import timedelta
from uuid import uuid4

import jwt
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Count, Max, Sum
from django.conf import settings
from django.utils import timezone
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


def issue_admin_token(user: User) -> str:
	now = timezone.now()
	return jwt.encode(
		{
			"sub": str(user.id),
			"type": "admin",
			"iat": now,
			"exp": now + timedelta(hours=8),
		},
		settings.SECRET_KEY,
		algorithm="HS256",
	)


def get_admin_user(request):
	auth_header = request.headers.get("Authorization", "")
	scheme, _, raw_token = auth_header.partition(" ")
	if scheme.lower() != "bearer" or not raw_token:
		return None
	try:
		payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=["HS256"])
	except jwt.PyJWTError:
		return None
	if payload.get("type") != "admin":
		return None
	return User.objects.filter(id=payload.get("sub"), is_active=True, is_staff=True).first()


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


class AdminLoginView(APIView):
	def post(self, request):
		username = (request.data.get("username") or "").strip()
		password = request.data.get("password") or ""
		if not username or not password:
			return Response({"message": "Логин и пароль обязательны"}, status=400)

		user = authenticate(request, username=username, password=password)
		if user is None or not user.is_staff:
			return Response({"message": "Неверный логин или пароль"}, status=401)

		return Response(
			{
				"token": issue_admin_token(user),
				"admin": {
					"id": user.id,
					"name": user.get_full_name() or user.username,
					"username": user.username,
					"email": user.email,
				},
			}
		)


class AdminDashboardView(APIView):
	def get(self, request):
		admin_user = get_admin_user(request)
		if admin_user is None:
			return Response({"message": "Требуется вход администратора"}, status=401)

		from mobile_api.models import CustomerProfile
		from partner_api.models import Booking

		customers = CustomerProfile.objects.select_related("user", "city").order_by("-created_at")
		partners = PartnerProfile.objects.select_related("user").order_by("-created_at")
		bookings = Booking.objects.all()
		bookings_by_phone = {
			row["client_phone"]: row
			for row in bookings.values("client_phone").annotate(
				visits=Count("id"),
				last_visit=Max("starts_at"),
				total_amount=Sum("final_price"),
			)
		}
		recent_customers = [
			{
				"id": customer.id,
				"name": customer.user.first_name or "Без имени",
				"email": customer.user.email or "",
				"phone": customer.phone,
				"city_name": customer.city.name if customer.city_id else "",
				"avatar_url": customer.avatar_url or None,
				"created_at": customer.created_at.isoformat(),
				"visits": bookings_by_phone.get(customer.phone, {}).get("visits", 0),
				"last_visit": (
					bookings_by_phone[customer.phone]["last_visit"].isoformat()
					if bookings_by_phone.get(customer.phone, {}).get("last_visit")
					else None
				),
				"total_amount": str(bookings_by_phone.get(customer.phone, {}).get("total_amount") or 0),
			}
			for customer in customers[:5]
		]
		partner_list = [
			{
				"id": partner.id,
				"name": partner.company_name or partner.user.get_full_name() or partner.user.username,
				"contact_name": partner.user.get_full_name() or partner.user.first_name or partner.user.email,
				"email": partner.user.email,
				"phone": partner.phone,
				"category": partner.business_category,
				"is_active": partner.user.is_active,
				"created_at": partner.created_at.isoformat(),
			}
			for partner in partners[:50]
		]

		return Response(
			{
				"admin": {
					"id": admin_user.id,
					"name": admin_user.get_full_name() or admin_user.username,
					"email": admin_user.email,
				},
				"metrics": {
					"customers_total": customers.count(),
					"subscriptions_active": 0,
					"customers_without_subscription": customers.count(),
					"customers_turnover": str(bookings.aggregate(total=Sum("final_price"))["total"] or 0),
					"partners_total": partners.count(),
					"partners_active": partners.filter(user__is_active=True).count(),
					"bookings_total": bookings.count(),
					"revenue_total": str(sum((booking.final_price for booking in bookings), start=0)),
				},
				"customers": recent_customers,
				"partners": partner_list,
			}
		)


class AdminPartnerStatusView(APIView):
	def post(self, request, partner_id: int):
		if get_admin_user(request) is None:
			return Response({"message": "Требуется вход администратора"}, status=status.HTTP_401_UNAUTHORIZED)

		is_active = request.data.get("is_active")
		if not isinstance(is_active, bool):
			return Response({"message": "Поле is_active должно быть логическим значением"}, status=status.HTTP_400_BAD_REQUEST)

		partner = PartnerProfile.objects.select_related("user").filter(id=partner_id, user_type="partner").first()
		if partner is None:
			return Response({"message": "Партнёр не найден"}, status=status.HTTP_404_NOT_FOUND)

		partner.user.is_active = is_active
		partner.user.save(update_fields=["is_active"])
		return Response({"id": partner.id, "is_active": partner.user.is_active})


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

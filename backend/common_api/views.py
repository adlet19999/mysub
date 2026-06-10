from uuid import uuid4

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PartnerProfile


class HealthView(APIView):
	def get(self, request):
		return Response({"ok": True, "service": "django-backend"})


class AuthRegisterView(APIView):
	def post(self, request):
		full_name = (request.data.get("full_name") or "").strip()
		phone = (request.data.get("phone") or "").strip()
		email = (request.data.get("email") or "").strip().lower()
		password = request.data.get("password") or ""
		user_type = ((request.data.get("user_type") or "partner").strip().lower())
		company_name = (request.data.get("company_name") or "").strip()
		address = (request.data.get("address") or "").strip()
		business_category = (request.data.get("business_category") or "").strip()

		if not full_name or not phone or not email or not password:
			return Response({"message": "full_name, phone, email, password обязательны"}, status=400)

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
			return Response({"message": "Неверный логин или пароль"}, status=401)

		profile = getattr(user, "partner_profile", None)
		user_type = profile.user_type if profile else "partner"
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
					"company_name": company_name,
					"address": address,
					"business_category": business_category,
				},
			}
		)

# Create your views here.

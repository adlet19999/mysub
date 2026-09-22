from rest_framework import serializers


class SendCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text='Номер в формате +7XXXXXXXXXX')


class VerifyCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text='Номер в формате +7XXXXXXXXXX')
    code = serializers.CharField(help_text='Временный код: 11111')


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class CustomerUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    city_id = serializers.CharField(required=False)
    city_name = serializers.CharField(required=False)
    language = serializers.ChoiceField(choices=['ru', 'kk', 'en'], required=False)


class ChildRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    date_of_birth = serializers.DateField(help_text='Дата в формате YYYY-MM-DD')
from rest_framework import serializers


class SendCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text='Номер в формате +7XXXXXXXXXX', default='+77001234567')


class VerifyCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text='Номер в формате +7XXXXXXXXXX', default='+77001234567')
    code = serializers.CharField(help_text='Одноразовый код из SMS', default='11111')


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(help_text='Refresh token, полученный при регистрации или входе')


class SendCodeResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text='Статус отправки SMS')
    expires_in = serializers.IntegerField(help_text='Срок действия кода в секундах')
    retry_after = serializers.IntegerField(help_text='Через сколько секунд можно запросить код повторно')


class TokenPairSerializer(serializers.Serializer):
    access_token = serializers.CharField(help_text='JWT для запросов к защищённым endpoint, действует 1 час')
    refresh_token = serializers.CharField(help_text='JWT для обновления сессии, хранится в защищённом хранилище')
    token_type = serializers.CharField(help_text='Тип токена для заголовка Authorization')
    expires_in = serializers.IntegerField(help_text='Срок действия access token в секундах')


class ChildSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, help_text='Передавайте только для уже созданного ребёнка')
    name = serializers.CharField(help_text='Имя ребёнка от 1 до 50 букв')
    date_of_birth = serializers.DateField(help_text='Дата в формате YYYY-MM-DD')
    age = serializers.IntegerField(required=False, read_only=True)


class CityResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text='Идентификатор города для передачи в city_id')
    name = serializers.CharField(help_text='Название города для отображения пользователю')


class CityListResponseSerializer(serializers.Serializer):
    data = CityResponseSerializer(many=True)


class CustomerResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    phone = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    email = serializers.EmailField(allow_null=True)
    avatar_url = serializers.URLField(allow_null=True)
    city_id = serializers.IntegerField(allow_null=True, help_text='ID выбранного города из GET /cities/')
    city_name = serializers.CharField(allow_null=True)
    language = serializers.ChoiceField(choices=['ru', 'kk', 'en'])
    is_profile_complete = serializers.BooleanField(help_text='true, если заполнены имя и город')
    agreement_accepted = serializers.BooleanField()
    agreement_version = serializers.CharField(allow_null=True)
    children = ChildSerializer(many=True)
    max_children = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class AuthenticationResponseSerializer(serializers.Serializer):
    user = CustomerResponseSerializer()
    tokens = TokenPairSerializer()
    is_new_user = serializers.BooleanField(help_text='true только после успешной регистрации нового клиента')


class RefreshTokenResponseSerializer(serializers.Serializer):
    tokens = TokenPairSerializer()


class CustomerUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, help_text='Имя от 2 до 100 символов')
    email = serializers.EmailField(required=False, allow_blank=True)
    avatar_url = serializers.URLField(required=False, allow_blank=True, help_text='URL фотографии пользователя')
    city_id = serializers.IntegerField(required=False, min_value=1, help_text='ID города из GET /cities/')
    language = serializers.ChoiceField(choices=['ru', 'kk', 'en'], required=False)
    agreement_accepted = serializers.BooleanField(required=False)
    agreement_version = serializers.CharField(required=False, allow_blank=True, max_length=40)
    children = ChildSerializer(required=False, many=True, help_text='Полный актуальный список детей, не более двух')
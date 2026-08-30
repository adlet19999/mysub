from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("common_api", "0005_partnerprofile_business_photo_urls"),
	]

	operations = [
		migrations.AddField(
			model_name="partnerprofile",
			name="must_change_password",
			field=models.BooleanField(default=False),
		),
	]
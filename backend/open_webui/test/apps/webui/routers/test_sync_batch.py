from test.util.abstract_integration_test import AbstractPostgresTest
from open_webui.models.users import Users
from open_webui.models.groups import Groups, GroupForm
import os


class TestSyncBatch(AbstractPostgresTest):
    BASE_PATH = "/api/internal/upsert-users"

    @classmethod
    def setup_class(cls):
        os.environ["OWUI_AUTH_TOKEN"] = "Bearer testtoken"
        super().setup_class()

    def setup_method(self):
        super().setup_method()
        Users.insert_new_user(
            id="owner",
            name="owner",
            email="owner@example.com",
            profile_image_url="/user.png",
            role="user",
        )
        Groups.insert_new_group("owner", GroupForm(name="Student", description="d"))

    def test_sync_user_creation(self):
        payload = {
            "users": [
                {
                    "name": "Jane Doe",
                    "email": "jane@example.com",
                    "role": "user",
                    "group": "Student",
                }
            ]
        }
        response = self.fast_api_client.post(
            self.create_url(""),
            json=payload,
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1
        assert data["received"] == 1
        assert data["failed"] == 0
        detail = data["results"][0]
        assert detail["status"] == "created"
        user = Users.get_user_by_email("jane@example.com")
        assert user is not None
        group = Groups.get_group_by_name("Student")
        assert user.id in group.user_ids

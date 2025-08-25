from test.util.abstract_integration_test import AbstractPostgresTest
from test.util.mock_user import mock_webui_user


class TestRetrieval(AbstractPostgresTest):
    BASE_PATH = "/api/v1/retrieval"

    def test_process_empty_file(self):
        from open_webui.models.files import Files, FileForm
        from open_webui.constants import ERROR_MESSAGES

        # Create an empty file entry in the database. The file has no content
        # and no backing path so the processing pipeline should detect that no
        # textual content is available.
        file = Files.insert_new_file(
            "1",
            FileForm(
                id="test-file",
                filename="empty.txt",
                path="",
                data={"content": ""},
                meta={"content_type": "text/plain"},
            ),
        )

        with mock_webui_user():
            response = self.fast_api_client.post(
                self.create_url("/process/file"),
                json={"file_id": file.id},
            )

        assert response.status_code == 400
        assert response.json() == {"detail": ERROR_MESSAGES.EMPTY_CONTENT}


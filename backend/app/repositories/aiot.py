from uuid import UUID

from psycopg.rows import dict_row

from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect


class AiotRepository:
    """Private metadata reads; caller must resolve the owner from authentication."""

    def __init__(self, settings: RuntimeSettings):
        self._settings = settings

    def get_job(self, owner_user_id: UUID, job_id: UUID) -> dict | None:
        with connect(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    "SELECT * FROM jobs WHERE id = %s AND owner_user_id = %s",
                    (job_id, owner_user_id),
                ).fetchone()

    def get_dataset(self, owner_user_id: UUID, dataset_id: UUID) -> dict | None:
        with connect(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    "SELECT * FROM datasets WHERE id = %s AND owner_user_id = %s",
                    (dataset_id, owner_user_id),
                ).fetchone()

    def get_model(self, owner_user_id: UUID, model_id: UUID) -> dict | None:
        with connect(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    "SELECT * FROM models WHERE id = %s AND owner_user_id = %s",
                    (model_id, owner_user_id),
                ).fetchone()

    def get_activation(self, owner_user_id: UUID, activation_id: UUID) -> dict | None:
        with connect(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    "SELECT * FROM model_activations WHERE id = %s AND owner_user_id = %s",
                    (activation_id, owner_user_id),
                ).fetchone()

    def get_active_model(self, owner_user_id: UUID) -> dict | None:
        with connect(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    "SELECT m.* FROM active_models a JOIN models m "
                    "ON (m.id, m.owner_user_id) = (a.model_id, a.owner_user_id) "
                    "WHERE a.owner_user_id = %s",
                    (owner_user_id,),
                ).fetchone()

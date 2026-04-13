from infrahub_sdk.client import InfrahubClient

from infrahub import config
from infrahub.core.migrations.graph.m070_check_optional_hfid_uniqueness import Migration070
from infrahub.core.migrations.shared import MigrationInput
from infrahub.database import InfrahubDatabase
from tests.helpers.test_app import TestInfrahubApp


class TestMigration070(TestInfrahubApp):
    """Verify that m070 reports schemas where an optional attribute with no default_value is
    referenced in human_friendly_id or uniqueness_constraints."""

    async def _load_violating_schema(self, client: InfrahubClient) -> None:
        # Loading this schema while strict mode is off bypasses the validator so we can
        # simulate a pre-existing deployment that has violations in the database.
        violating_schema: dict = {
            "version": "1.0",
            "generics": [
                {
                    "name": "Gadget",
                    "namespace": "Testing",
                    "human_friendly_id": ["name__value", "serial__value"],
                    "uniqueness_constraints": [["serial__value"]],
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                        {"name": "serial", "kind": "Text", "optional": True},
                    ],
                }
            ],
            "nodes": [
                {
                    "name": "Widget",
                    "namespace": "Testing",
                    "inherit_from": ["TestingGadget"],
                }
            ],
        }
        response = await client.schema.load(schemas=[violating_schema])
        assert len(response.errors) == 0, response.errors

    async def test_migration_clean_and_with_violations(
        self, db: InfrahubDatabase, client: InfrahubClient
    ) -> None:
        strict_mode_original = config.SETTINGS.main.schema_strict_mode

        try:
            # Baseline: the default schema has no violations, migration should report nothing.
            migration = Migration070(db=db)
            baseline_result = await migration.execute(migration_input=MigrationInput(db=db))
            assert not baseline_result.errors, (
                f"Expected no errors on baseline schema, got: {baseline_result.errors}"
            )

            # Simulate a pre-existing deployment by loading a violating schema with strict mode off.
            config.SETTINGS.main.schema_strict_mode = False
            await self._load_violating_schema(client=client)

            # Run the migration — it should report the violation regardless of strict mode
            execution_result = await migration.execute(migration_input=MigrationInput(db=db))

            assert execution_result.errors, "Migration should return errors when violations exist"
            header = execution_result.errors[0]
            assert "INFRAHUB_SCHEMA_STRICT_MODE=false" in header, (
                "Migration header should explain how to bypass the validator"
            )

            violation_reports = execution_result.errors[1:]
            matching = [
                msg
                for msg in violation_reports
                if "'serial'" in msg and "TestingGadget" in msg
            ]
            assert matching, f"Expected a violation for 'serial' of TestingGadget, got: {violation_reports}"
        finally:
            config.SETTINGS.main.schema_strict_mode = strict_mode_original

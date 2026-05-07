from infrahub.core.branch import Branch
from infrahub.core.migrations.graph.m070_internal_group_type_on_system_kinds import (
    INTERNAL_GROUP_KINDS,
    Migration070,
)
from infrahub.core.migrations.shared import MigrationInput
from infrahub.core.timestamp import current_timestamp
from infrahub.database import InfrahubDatabase


async def test_migration_070(db: InfrahubDatabase, default_branch: Branch) -> None:
    """Existing system-managed groups with group_type='default' should be flipped to 'internal',
    while user-managed groups (CoreStandardGroup) should be left untouched."""

    create_test_data_query = """
    // shared 'default' value reused by every group_type attribute below
    CREATE (default_value:AttributeValue:AttributeValueIndexed {value: "default", is_default: true})

    // one instance per system-managed kind, plus a user-managed CoreStandardGroup as a control
    CREATE (account:Node:CoreAccountGroup {uuid: "account-uuid"})
    CREATE (generator:Node:CoreGeneratorGroup {uuid: "generator-uuid"})
    CREATE (generator_aware:Node:CoreGeneratorAwareGroup {uuid: "generator-aware-uuid"})
    CREATE (graphql:Node:CoreGraphQLQueryGroup {uuid: "graphql-uuid"})
    CREATE (repository:Node:CoreRepositoryGroup {uuid: "repository-uuid"})
    CREATE (standard:Node:CoreStandardGroup {uuid: "standard-uuid"})

    CREATE (account_attr:Attribute {name: "group_type"})
    CREATE (generator_attr:Attribute {name: "group_type"})
    CREATE (generator_aware_attr:Attribute {name: "group_type"})
    CREATE (graphql_attr:Attribute {name: "group_type"})
    CREATE (repository_attr:Attribute {name: "group_type"})
    CREATE (standard_attr:Attribute {name: "group_type"})

    CREATE (account)-[:HAS_ATTRIBUTE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(account_attr)
    CREATE (generator)-[:HAS_ATTRIBUTE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(generator_attr)
    CREATE (generator_aware)-[:HAS_ATTRIBUTE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(generator_aware_attr)
    CREATE (graphql)-[:HAS_ATTRIBUTE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(graphql_attr)
    CREATE (repository)-[:HAS_ATTRIBUTE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(repository_attr)
    CREATE (standard)-[:HAS_ATTRIBUTE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(standard_attr)

    CREATE (account_attr)-[:HAS_VALUE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(default_value)
    CREATE (generator_attr)-[:HAS_VALUE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(default_value)
    CREATE (generator_aware_attr)-[:HAS_VALUE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(default_value)
    CREATE (graphql_attr)-[:HAS_VALUE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(default_value)
    CREATE (repository_attr)-[:HAS_VALUE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(default_value)
    CREATE (standard_attr)-[:HAS_VALUE {branch: $branch, branch_level: 1, status: "active", from: $at}]->(default_value)
    """
    await db.execute_query(
        query=create_test_data_query,
        params={"branch": default_branch.name, "at": current_timestamp()},
    )

    migration = Migration070()
    execution_result = await migration.execute(migration_input=MigrationInput(db=db))
    assert not execution_result.errors

    validation_result = await migration.validate_migration(db=db)
    assert not validation_result.errors

    # every system-managed kind should now resolve to group_type='internal'
    affected_query = """
    MATCH (n:Node)
    WHERE any(label IN labels(n) WHERE label IN $kinds)
    MATCH (n)-[:HAS_ATTRIBUTE]->(:Attribute {name: "group_type"})-[hv:HAS_VALUE]->(v:AttributeValue)
    WHERE hv.status = "active" AND hv.to IS NULL
    RETURN n.uuid AS uuid, v.value AS group_type
    ORDER BY n.uuid
    """
    results = await db.execute_query(query=affected_query, params={"kinds": INTERNAL_GROUP_KINDS})
    assert len(results) == 5
    for row in results:
        assert row.get("group_type") == "internal"

    # the CoreStandardGroup control must still read 'default'
    control_query = """
    MATCH (n:Node:CoreStandardGroup {uuid: "standard-uuid"})
    MATCH (n)-[:HAS_ATTRIBUTE]->(:Attribute {name: "group_type"})-[hv:HAS_VALUE]->(v:AttributeValue)
    WHERE hv.status = "active" AND hv.to IS NULL
    RETURN v.value AS group_type
    """
    results = await db.execute_query(query=control_query)
    assert len(results) == 1
    assert results[0].get("group_type") == "default"

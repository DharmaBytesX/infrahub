from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from infrahub.core.migrations.shared import MigrationResult
from infrahub.core.query import Query, QueryType

from ..shared import GraphMigration

if TYPE_CHECKING:
    from infrahub.database import InfrahubDatabase


INTERNAL_GROUP_KINDS = [
    "CoreAccountGroup",
    "CoreGeneratorGroup",
    "CoreGeneratorAwareGroup",
    "CoreGraphQLQueryGroup",
    "CoreRepositoryGroup",
]


class Migration070Query01(Query):
    """Flip group_type from 'default' to 'internal' on existing system-managed group instances.

    The schema now defaults group_type to 'internal' for these kinds, but existing instances
    created before the schema change still carry 'default' and would leak into user-facing
    'add to group' selectors that filter on group_type.
    """

    name = "migration_070_01"
    type: QueryType = QueryType.WRITE

    async def query_init(self, db: InfrahubDatabase, **kwargs: dict[str, Any]) -> None:  # noqa: ARG002
        self.params["at"] = self.at.to_string()
        self.params["kinds"] = INTERNAL_GROUP_KINDS

        query = """
// match every active group_type='default' value on instances of the affected kinds
MATCH (n:Node)
WHERE any(label IN labels(n) WHERE label IN $kinds)
MATCH p = (n)-[:HAS_ATTRIBUTE]->(attr:Attribute {name: "group_type"})-[hv:HAS_VALUE]->(:AttributeValue {value: "default"})
WHERE all(r IN relationships(p) WHERE r.status = "active" AND r.to IS NULL)

// close the edge to the 'default' value
SET hv.to = $at

// reuse or create the 'internal' value node
MERGE (new_value:AttributeValue:AttributeValueIndexed {value: "internal", is_default: true})

// link each affected attribute to the 'internal' value, preserving branch metadata
CREATE (attr)-[new_hv:HAS_VALUE]->(new_value)
SET new_hv = properties(hv)
SET new_hv.from = $at, new_hv.to = NULL
        """
        self.add_to_query(query)
        self.return_labels = ["new_value"]


class Migration070(GraphMigration):
    name: str = "070_internal_group_type_on_system_kinds"
    queries: Sequence[type[Query]] = [Migration070Query01]
    minimum_version: int = 69

    async def validate_migration(self, db: InfrahubDatabase) -> MigrationResult:  # noqa: ARG002
        return MigrationResult()

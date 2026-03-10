"""Permission constants — stub for Phase 2a, full ACL in Step 3.

Permission names follow a dot-separated namespace:
    <domain>.<action>

Examples:
    fields.read, fields.write, fields.delete
    users.read, users.create, users.update
    admin.users, admin.groups, admin.system
"""

# Auth / Users
USERS_READ = "users.read"
USERS_CREATE = "users.create"
USERS_UPDATE = "users.update"
USERS_DELETE = "users.delete"

# Groups
GROUPS_READ = "groups.read"
GROUPS_CREATE = "groups.create"
GROUPS_UPDATE = "groups.update"
GROUPS_DELETE = "groups.delete"

# Fields (placeholder — defined in FieldService step)
FIELDS_READ = "fields.read"
FIELDS_WRITE = "fields.write"
FIELDS_DELETE = "fields.delete"

# Admin
ADMIN_USERS = "admin.users"
ADMIN_GROUPS = "admin.groups"
ADMIN_SYSTEM = "admin.system"

# Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for managing database schema migrations.

## Quick Reference

```bash
# Create a new migration after changing models
alembic revision --autogenerate -m "Description of changes"

# Apply all pending migrations
alembic upgrade head

# Revert to a previous migration
alembic downgrade -1

# View migration history
alembic history

# Check current migration status
alembic current
```

## Workflow

### When you modify a model:

1. Update the model in `src/models/` (e.g., `src/models/task.py`)
2. Create a migration:
   ```bash
   alembic revision --autogenerate -m "Brief description of changes"
   ```
3. Review the generated migration file in `alembic/versions/`
4. Test the migration on a development database
5. Commit the migration file to git

### Running migrations in development:

```bash
# Apply all pending migrations
alembic upgrade head

# For local testing with in-memory SQLite
# Migrations are not needed - in-memory databases are created fresh
# See tests/conftest.py for test database setup
```

### For production:

Always run migrations before deploying:
```bash
alembic upgrade head
```

## Migration Files

Migrations are stored in `alembic/versions/` with filenames like:
- `7ae29958397f_add_initiative_id_to_tasks_table.py`

Each migration file contains:
- `upgrade()` - Schema changes to apply
- `downgrade()` - How to revert the changes
- Revision ID and dependency information

## Common Tasks

### Creating a migration for a new column:

```bash
# 1. Add to model
initiative_id: Mapped[int | None] = mapped_column(
    Integer, ForeignKey("initiatives.id", ondelete="SET NULL"), nullable=True
)

# 2. Generate migration
alembic revision --autogenerate -m "Add initiative_id to tasks"

# 3. Apply it
alembic upgrade head
```

### Manual migration (if autogenerate doesn't detect changes):

```bash
# Create empty migration
alembic revision -m "Manual migration description"

# Edit the generated file with manual SQL operations
```

## Troubleshooting

### Migration doesn't detect my changes:

- Ensure you imported the model in `alembic/env.py` (already done via `from src.models.database import Base`)
- Check that the model is registered with the `Base` metadata
- Try adjusting `compare_type=True` and `compare_server_default=True` in `alembic/env.py`

### Can't apply migration:

```bash
# Check current migration status
alembic current

# View recent migrations
alembic history -r -5
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy ORM Documentation](https://docs.sqlalchemy.org/en/20/orm/)

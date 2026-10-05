"""add product catalog details

Revision ID: 0ab8b7d097ac
Revises: a1b2c3d4e5f6
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0ab8b7d097ac"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the new catalog columns as nullable first because the existing
    # products already exist in the database.
    op.add_column(
        "products",
        sa.Column("name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("sku", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("category", sa.String(length=50), nullable=True),
    )

    # Update the existing products with application-level catalog details.
    catalog = [
        ("P0001", "Wireless Headphones", "WH-001", "Electronics"),
        ("P0002", "Cotton T-Shirt", "TS-002", "Clothing"),
        ("P0003", "Wooden Chair", "CH-003", "Furniture"),
        ("P0004", "Smartphone", "SP-004", "Electronics"),
        ("P0005", "Running Shoes", "RS-005", "Clothing"),
        ("P0006", "LED Desk Lamp", "DL-006", "Electronics"),
        ("P0007", "Kitchen Blender", "KB-007", "Electronics"),
        ("P0008", "Teddy Bear", "TB-008", "Toys"),
        ("P0009", "Office Desk", "OD-009", "Furniture"),
        ("P0010", "Organic Rice", "OR-010", "Groceries"),
        ("P0011", "Bluetooth Speaker", "BS-011", "Electronics"),
        ("P0012", "Denim Jeans", "DJ-012", "Clothing"),
        ("P0013", "Bookshelf", "BS-013", "Furniture"),
        ("P0014", "Board Game", "BG-014", "Toys"),
        ("P0015", "Coffee Beans", "CB-015", "Groceries"),
        ("P0016", "Winter Jacket", "WJ-016", "Clothing"),
        ("P0017", "Dining Table", "DT-017", "Furniture"),
        ("P0018", "Action Figure", "AF-018", "Toys"),
        ("P0019", "Fresh Juice", "FJ-019", "Groceries"),
        ("P0020", "Wireless Mouse", "WM-020", "Electronics"),
    ]

    for product_id, name, sku, category in catalog:
        op.execute(
            sa.text(
                """
                UPDATE products
                SET name = :name,
                    sku = :sku,
                    category = :category
                WHERE product_id = :product_id
                """
            ).bindparams(
                product_id=product_id,
                name=name,
                sku=sku,
                category=category,
            )
        )

    # Keep any nonstandard product IDs already in the database migratable too.
    # The known catalog above receives descriptive names; unknown products get
    # stable generated values so the columns can safely become non-null.
    op.execute(
        sa.text(
            """
            UPDATE products
            SET name = 'Product ' || product_id,
                sku = 'SKU-' || product_id,
                category = 'Uncategorized'
            WHERE name IS NULL OR sku IS NULL OR category IS NULL
            """
        )
    )

    # Make the catalog fields required after the existing products
    # have been populated.
    op.alter_column(
        "products",
        "name",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "products",
        "sku",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.alter_column(
        "products",
        "category",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    # Every product gets its own SKU.
    op.create_unique_constraint(
        "uq_products_sku",
        "products",
        ["sku"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_sku", "products", type_="unique")
    op.drop_column("products", "category")
    op.drop_column("products", "sku")
    op.drop_column("products", "name")

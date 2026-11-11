"""Category management API routes for PaisaClarity (Phase 6)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, Category, Transaction
from schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    category_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all categories available to the user:
    Both system categories (is_system=True) and user-defined custom categories.
    """
    query = db.query(Category).filter(
        or_(
            Category.is_system == True,
            Category.user_id == current_user.id,
        )
    )
    if category_type:
        query = query.filter(Category.category_type == category_type.lower().strip())

    categories = query.order_by(Category.is_system.desc(), Category.name.asc()).all()
    return categories


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_in: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new custom category for the authenticated user."""
    name_clean = category_in.name.strip()
    
    # Check if a custom category with this name already exists for this user
    existing_user_cat = (
        db.query(Category)
        .filter(Category.user_id == current_user.id, Category.name.ilike(name_clean))
        .first()
    )
    if existing_user_cat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category '{name_clean}' already exists in your custom categories",
        )

    cat = Category(
        user_id=current_user.id,
        name=name_clean,
        category_type=category_in.category_type.lower().strip(),
        is_system=False,
        icon=category_in.icon,
        color=category_in.color,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a single category."""
    cat = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            or_(Category.is_system == True, Category.user_id == current_user.id),
        )
        .first()
    )
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return cat


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_in: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a custom category. System categories cannot be modified."""
    cat = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            or_(Category.is_system == True, Category.user_id == current_user.id),
        )
        .first()
    )
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if cat.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System categories cannot be modified",
        )

    old_name = cat.name
    if category_in.name is not None:
        name_clean = category_in.name.strip()
        if not name_clean:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name cannot be empty")
        # Check duplicate
        dup = (
            db.query(Category)
            .filter(
                Category.user_id == current_user.id,
                Category.name.ilike(name_clean),
                Category.id != cat.id,
            )
            .first()
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{name_clean}' already exists",
            )
        cat.name = name_clean

        # Synchronize all existing user transactions referencing this category_id
        # to ensure category_id and denormalized category string remain strictly synchronized!
        db.query(Transaction).filter(
            Transaction.user_id == current_user.id,
            Transaction.category_id == cat.id,
        ).update({"category": name_clean}, synchronize_session=False)

    if category_in.category_type is not None:
        valid_types = ("expense", "income", "transfer", "investment")
        t_clean = category_in.category_type.lower().strip()
        if t_clean not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"category_type must be one of {valid_types}",
            )
        cat.category_type = t_clean

    if category_in.icon is not None:
        cat.icon = category_in.icon
    if category_in.color is not None:
        cat.color = category_in.color

    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_200_OK)
def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Safely delete a custom category.
    System categories cannot be deleted.
    When a custom category is deleted, transactions referencing it will have
    category_id set to NULL (via ON DELETE SET NULL), while their historical
    denormalized 'category' string is preserved to protect analytics continuity.
    """
    cat = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            or_(Category.is_system == True, Category.user_id == current_user.id),
        )
        .first()
    )
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if cat.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System categories cannot be deleted",
        )

    # Note: Foreign key on Transaction.category_id has ondelete="SET NULL".
    # We explicitly nullify category_id on user transactions to ensure
    # SQLite and PostgreSQL behave identically in all environments.
    db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.category_id == cat.id,
    ).update({"category_id": None}, synchronize_session=False)

    db.delete(cat)
    db.commit()
    return {"status": "ok", "message": f"Category '{cat.name}' deleted successfully"}

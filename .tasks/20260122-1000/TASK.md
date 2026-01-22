# Task: Add `feed_id` to `item_hash`

- STATUS: COMPLETED
- PRIORITY: 2

## Objective
Scope item deduplication to specific feeds by adding a `feed_id` column to the `item_hash` table. This allows the same content (same hash) to be processed independently if it appears in different feeds, while maintaining deduplication within a single feed.

## Research
- **Model:** `app/models/item_hash.py` (Currently `id`, `hash`).
- **Repository:** `app/services/repositories/item_hash.py` (Methods `contains`, `save`).
- **Middleware:** `app/middlewares/hash.py` (Uses repository to deduplicate).
- **Existing Data:** `item_hash` table contains global hashes without feed context.

## Plan

### 1. Database Schema Change
- [x] Modify `app/models/item_hash.py`:
  - Add `feed_id` column.
  - Type: `int` (Mapped).
  - Constraint: `ForeignKey("feed.id")`.
  - Nullable: `True` (Essential for existing rows).

### 2. Migration
- [x] Generate an Alembic migration (`alembic revision --autogenerate`).
- [x] This will add `feed_id` to `item_hash`, defaulting to `NULL` for existing rows.

### 3. Code Implementation
- [x] **Repository (`app/services/repositories/item_hash.py`):**
  - Update `save(hash)` to `save(hash, feed_id)`.
  - Update `contains(hash)` to `contains(hash, feed_id)`.
  - **Logic Update:**
    - `save`: Store the `feed_id`.
    - `contains`: Check if the hash exists for *this* feed OR if it exists globally (NULL `feed_id`).
- [x] **Middleware (`app/middlewares/hash.py`):**
  - Extract `feed.id` from the `feed` object.
  - Pass `feed.id` to `ItemsHashRepository.contains` and `ItemsHashRepository.save`.

## Problems & Handling Strategy

### Problem: Existing Data (Legacy Hashes)
The `item_hash` table is populated with hashes that have `feed_id = NULL`. We do not know which feed generated them.

### Strategy: "Claim" Legacy Hashes (Lazy Migration)
We will lazily migrate hashes from "Global" (`NULL`) to "Scoped" (`feed_id`) when they are encountered.

**Revised Logic for `contains(hash, feed_id)`:**
1. Check if hash exists for the specific `feed_id`.
   - If **Found**: Return `True` (Duplicate).
2. Check if hash exists globally (`feed_id IS NULL`).
   - If **Found**:
     - **Action**: "Claim" the hash. Update the existing row sets `feed_id = current_feed_id`.
     - **Return**: `True` (Duplicate).
   - If **Not Found**:
     - **Return**: `False` (New Item).

**Consequence:**
- The first feed to encounter a legacy item will "claim" the hash.
- **Side Effect:** If another feed shares this same item, it will no longer see the global blocker. It will treat the item as "New" (since the hash is now owned by the first feed) and save a *new* hash row `(Hash, OtherFeedID)`. This effectively re-enables the item for the other feed, which is acceptable (or desired) for strictly scoped feeds.

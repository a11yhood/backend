# API Reference

Complete reference for all REST API endpoints in a11yhood.

## Base URL

All API endpoints are relative to `/api`


## Response Format

## Timestamp Contract

All timestamp fields in the API use UTC ISO 8601 strings with a time component.

- Example: `2026-04-16T00:00:00+00:00`
- Applies to fields such as `created_at`, `updated_at`, `joined_at`, `last_active`, `timestamp`, `publish_date`, `published_at`, `reviewed_at`, and `source_last_updated`
- Date-only strings such as `2026-04-16` are not part of the API contract
- Clients should parse these values as RFC 3339 / ISO 8601 date-time strings, not Unix milliseconds

### Success Response

```json
{
  "data": { ... }
}
```

### Error Response

```json
{
  "message": "Error description",
  "status": 400,
  "data": { ... }
}
```

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Sign in required |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found |
| 500 | Internal Server Error |

---

## Users

### Get All Users

```http
GET /api/users
GET /api/users?role=moderator
```

**Query Parameters:**
- `role` (optional): Filter by user role (`moderator`, `admin`)

**Response:**
```json
[
  {
    "id": "12345",
    "githubId": "12345",
    "login": "johndoe",
    "avatarUrl": "https://...",
    "email": "john@example.com",
    "displayName": "John Doe",
    "bio": "Accessibility advocate",
    "location": "San Francisco",
    "website": "https://example.com",
    "role": "user",
    "joinedAt": "2026-04-16T00:00:00+00:00",
    "lastActive": "2026-04-16T12:34:56+00:00",
    "productsSubmitted": 5,
    "reviewsWritten": 12,
    "ratingsGiven": 34,
    "discussionsParticipated": 8
  }
]
```

### Get User Account

```http
GET /api/users/:githubId
```

**Parameters:**
- `githubId`: GitHub user ID

**Response:**
```json
{
  "id": "12345",
  "githubId": "12345",
  "login": "johndoe",
  ...
}
```

Returns `null` if user not found.

### Create or Update User Account

```http
PUT /api/users/:githubId
```

**Parameters:**
- `githubId`: GitHub user ID

**Body:**
```json
{
  "login": "johndoe",
  "avatarUrl": "https://...",
  "email": "john@example.com"
}
```

**Response:**
```json
{
  "id": "12345",
  "githubId": "12345",
  "login": "johndoe",
  ...
}
```

### Update User Profile

```http
PATCH /api/users/:githubId/profile
```

**Parameters:**
- `githubId`: GitHub user ID

**Body:**
```json
{
  "displayName": "John Doe",
  "bio": "Accessibility advocate",
  "location": "San Francisco",
  "website": "https://example.com"
}
```

**Response:**
```json
{
  "id": "12345",
  ...
}
```

### Set User Role

```http
PATCH /api/users/:githubId/role
```

**Permissions:** Admin only

**Parameters:**
- `githubId`: GitHub user ID

**Body:**
```json
{
  "role": "moderator"
}
```

**Response:**
```json
{
  "id": "12345",
  "role": "moderator",
  ...
}
```

### Increment User Stat

```http
POST /api/users/:githubId/stats/:stat
```

**Parameters:**
- `githubId`: GitHub user ID
- `stat`: One of `productsSubmitted`, `reviewsWritten`, `ratingsGiven`, `discussionsParticipated`

**Response:**
```json
{
  "success": true
}
```

### Get User Activities

```http
GET /api/users/:userId/activities?limit=50
```

**Parameters:**
- `userId`: User ID

**Query Parameters:**
- `limit` (optional): Number of activities to return (default: 50)

**Response:**
```json
[
  {
    "userId": "12345",
    "type": "product_submit",
    "productId": "prod-1",
    "timestamp": "2026-04-16T12:34:56+00:00",
    "metadata": { ... }
  }
]
```

### Get User Statistics

```http
GET /api/users/:userId/stats
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
{
  "productsSubmitted": 5,
  "reviewsWritten": 12,
  "ratingsGiven": 34,
  "discussionsParticipated": 8,
  "totalContributions": 59
}
```

### Get User's Products

```http
GET /api/users/:userId/products
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "id": "prod-1",
    "name": "Accessible Keyboard",
    "submittedBy": "12345",
    ...
  }
]
```

### Export User Data

```http
GET /api/users/:userId/export
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
{
  "account": { ... },
  "products": [ ... ],
  "reviews": [ ... ],
  "ratings": [ ... ],
  "discussions": [ ... ],
  "activities": [ ... ]
}
```

---

## Products

### Get All Products

```http
GET /api/products
```

**Response:**
```json
[
  {
    "id": "prod-1",
    "name": "Accessible Keyboard",
    "type": "Hardware",
    "source": "Thingiverse",
    "sourceUrl": "https://...",
    "description": "...",
    "imageId": "8be8bb31-8f3d-4f53-8bd1-c167a0c5f184",
    "imageAlt": "Keyboard with large keys",
    "tags": ["keyboard", "typing", "accessibility"],
    "createdAt": 1704067200000,
    "submittedBy": "12345",
    "origin": "user-submitted",
    "lastEditedAt": 1704153600000,
    "lastEditedBy": "admin",
    "banned": false,
    "ownerIds": ["12345"]
  }
]
```

Use `GET /api/images/{imageId}` to render image bytes for uploaded images or follow
redirects for external image sources.

### Get Single Product

```http
GET /api/products/:id
```

**Parameters:**
- `id`: Product ID

**Response:**
```json
{
  "id": "prod-1",
  "name": "Accessible Keyboard",
  ...
}
```

Returns `null` if not found.

### Create Product

```http
POST /api/products
```

**Body:**
```json
{
  "name": "Accessible Keyboard",
  "type": "Hardware",
  "source": "User",
  "description": "A keyboard designed for accessibility",
  "tags": ["keyboard", "typing"],
  "submittedBy": "12345",
  "origin": "user-submitted",
  "ownerIds": ["12345"]
}
```

**Response:**
```json
{
  "id": "prod-new",
  "name": "Accessible Keyboard",
  "createdAt": 1704153600000,
  ...
}
```

### Update Product

```http
PATCH /api/products/:id
```

**Permissions:** Owner, Moderator, or Admin

**Parameters:**
- `id`: Product ID

**Body:**
```json
{
  "updates": {
    "name": "Updated Name",
    "description": "Updated description",
    "tags": ["new", "tags"]
  },
  "editorId": "12345"
}
```

**Response:**
```json
{
  "id": "prod-1",
  "name": "Updated Name",
  "lastEditedAt": 1704153600000,
  "lastEditedBy": "12345",
  ...
}
```

### Delete Product

```http
DELETE /api/products/:id
```

**Permissions:** Admin only

**Parameters:**
- `id`: Product ID

**Response:**
```json
{
  "success": true
}
```

### Delete Products by Source

```http
DELETE /api/products/source/:source
```

**Permissions:** Admin only

**Parameters:**
- `source`: Source name (e.g., "Thingiverse")

**Response:**
```json
{
  "deletedCount": 15
}
```

### Ban Product

```http
POST /api/products/:id/ban
```

**Permissions:** Moderator or Admin

**Parameters:**
- `id`: Product ID

**Body:**
```json
{
  "reason": "Spam content",
  "bannedBy": "admin-id"
}
```

**Response:**
```json
{
  "id": "prod-1",
  "banned": true,
  "bannedAt": 1704153600000,
  "bannedBy": "admin-id",
  "bannedReason": "Spam content",
  ...
}
```

### Unban Product

```http
POST /api/products/:id/unban
```

**Permissions:** Moderator or Admin

**Parameters:**
- `id`: Product ID

**Response:**
```json
{
  "id": "prod-1",
  "banned": false,
  ...
}
```

### Add Product Manager

```http
POST /api/products/:id/owners
```

**Permissions:** Existing owner, Moderator, or Admin

**Parameters:**
- `id`: Product ID

**Body:**
```json
{
  "userId": "67890"
}
```

**Response:**
```json
{
  "id": "prod-1",
  "ownerIds": ["12345", "67890"],
  ...
}
```

### Remove Product Manager

```http
DELETE /api/products/:id/owners/:userId
```

**Permissions:** Existing owner, Moderator, or Admin

**Parameters:**
- `id`: Product ID
- `userId`: User ID to remove

**Response:**
```json
{
  "id": "prod-1",
  "ownerIds": ["12345"],
  ...
}
```

### Get Product Managers

```http
GET /api/products/:id/owners
```

**Parameters:**
- `id`: Product ID

**Response:**
```json
[
  {
    "id": "12345",
    "login": "johndoe",
    "avatarUrl": "https://...",
    ...
  }
]
```

### Get Products by Owner

```http
GET /api/products/owner/:userId
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "id": "prod-1",
    "name": "Accessible Keyboard",
    "ownerIds": ["12345"],
    ...
  }
]
```

---

## Ratings

### Get All Ratings

```http
GET /api/ratings
```

**Response:**
```json
[
  {
    "productId": "prod-1",
    "userId": "12345",
    "rating": 5,
    "createdAt": 1704067200000
  }
]
```

### Create Rating

```http
POST /api/ratings
```

**Body:**
```json
{
  "productId": "prod-1",
  "userId": "12345",
  "rating": 5
}
```

**Response:**
```json
{
  "productId": "prod-1",
  "userId": "12345",
  "rating": 5,
  "createdAt": 1704153600000
}
```

### Update Rating

```http
PUT /api/ratings/:productId/:userId
```

**Parameters:**
- `productId`: Product ID
- `userId`: User ID

**Body:**
```json
{
  "rating": 4
}
```

**Response:**
```json
{
  "productId": "prod-1",
  "userId": "12345",
  "rating": 4,
  "createdAt": 1704067200000
}
```

### Get User's Ratings

```http
GET /api/users/:userId/ratings
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "productId": "prod-1",
    "userId": "12345",
    "rating": 5,
    "createdAt": 1704067200000
  }
]
```

---

## Reviews

### Get All Reviews

```http
GET /api/reviews
```

**Response:**
```json
[
  {
    "id": "review-1",
    "productId": "prod-1",
    "userId": "12345",
    "userName": "johndoe",
    "content": "Great product!",
    "createdAt": 1704067200000
  }
]
```

### Create Review

```http
POST /api/reviews
```

**Body:**
```json
{
  "productId": "prod-1",
  "userId": "12345",
  "userName": "johndoe",
  "content": "Great product!"
}
```

**Response:**
```json
{
  "id": "review-new",
  "productId": "prod-1",
  "userId": "12345",
  "userName": "johndoe",
  "content": "Great product!",
  "createdAt": 1704153600000
}
```

### Get User's Reviews

```http
GET /api/users/:userId/reviews
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "id": "review-1",
    "productId": "prod-1",
    "userId": "12345",
    ...
  }
]
```

---

## Discussions

### Get All Discussions

```http
GET /api/discussions
```

**Response:**
```json
[
  {
    "id": "disc-1",
    "productId": "prod-1",
    "userId": "12345",
    "userName": "johndoe",
    "content": "Has anyone tried this?",
    "parentId": null,
    "createdAt": 1704067200000
  },
  {
    "id": "disc-2",
    "productId": "prod-1",
    "userId": "67890",
    "userName": "janedoe",
    "content": "Yes, it works great!",
    "parentId": "disc-1",
    "createdAt": 1704153600000
  }
]
```

### Create Discussion or Reply

```http
POST /api/discussions
```

**Body:**
```json
{
  "productId": "prod-1",
  "userId": "12345",
  "userName": "johndoe",
  "content": "Has anyone tried this?",
  "parentId": null
}
```

For replies, include `parentId`:
```json
{
  "productId": "prod-1",
  "userId": "67890",
  "userName": "janedoe",
  "content": "Yes, it works great!",
  "parentId": "disc-1"
}
```

**Response:**
```json
{
  "id": "disc-new",
  "productId": "prod-1",
  "userId": "12345",
  "userName": "johndoe",
  "content": "Has anyone tried this?",
  "parentId": null,
  "createdAt": 1704153600000
}
```

### Get User's Discussions

```http
GET /api/users/:userId/discussions
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "id": "disc-1",
    "productId": "prod-1",
    "userId": "12345",
    ...
  }
]
```

---

## Blog Posts

### Get All Blog Posts

```http
GET /api/blog-posts
GET /api/blog-posts?includeUnpublished=true
```

**Query Parameters:**
- `includeUnpublished` (optional): Include unpublished posts (admin only, default: false)

**Response:**
```json
[
  {
    "id": "post-1",
    "title": "Welcome to a11yhood",
    "slug": "welcome-to-a11yhood",
    "content": "# Welcome\n\nContent in markdown...",
    "excerpt": "Short preview text",
    "headerImageId": "5e130167-b63e-4b4a-a758-5fce1f6c1804",
    "headerImageAlt": "Blog header",
    "authorId": "12345",
    "authorName": "John Doe",
    "authorIds": ["12345", "67890"],
    "authorNames": ["John Doe", "Jane Doe"],
    "createdAt": 1704067200000,
    "updatedAt": 1704153600000,
    "publishDate": 1704067200000,
    "published": true,
    "publishedAt": 1704067200000,
    "tags": ["announcement", "welcome"],
    "featured": true
  }
]
```

### Get Blog Post by ID

```http
GET /api/blog-posts/:id
```

**Parameters:**
- `id`: Blog post ID

**Response:**
```json
{
  "id": "post-1",
  "title": "Welcome to a11yhood",
  ...
}
```

### Get Blog Post by Slug

```http
GET /api/blog-posts/slug/:slug
```

**Parameters:**
- `slug`: Blog post slug (e.g., "welcome-to-a11yhood")

**Response:**
```json
{
  "id": "post-1",
  "title": "Welcome to a11yhood",
  "slug": "welcome-to-a11yhood",
  ...
}
```

### Create Blog Post

```http
POST /api/blog-posts
```

**Permissions:** Admin only

**Body:**
```json
{
  "title": "New Blog Post",
  "slug": "new-blog-post",
  "content": "# Hello\n\nMarkdown content...",
  "excerpt": "Short preview",
  "authorId": "12345",
  "authorName": "John Doe",
  "published": false
}
```

**Response:**
```json
{
  "id": "post-new",
  "title": "New Blog Post",
  "createdAt": 1704153600000,
  "updatedAt": 1704153600000,
  ...
}
```

### Update Blog Post

```http
PATCH /api/blog-posts/:id
```

**Permissions:** Admin only

**Parameters:**
- `id`: Blog post ID

**Body:**
```json
{
  "title": "Updated Title",
  "content": "Updated content",
  "published": true
}
```

**Response:**
```json
{
  "id": "post-1",
  "title": "Updated Title",
  "updatedAt": 1704153600000,
  ...
}
```

### Delete Blog Post

```http
DELETE /api/blog-posts/:id
```

**Permissions:** Admin only

**Parameters:**
- `id`: Blog post ID

**Response:**
```json
{
  "success": true
}
```

---

## Collections

### Collection Object

Collection responses use snake_case field names:

```json
{
  "id": "cf4d6c2e-8d8b-4b6e-a0aa-8f07d9a0a1a9",
  "slug": "my-favorites",
  "name": "My Favorites",
  "description": "Products I love",
  "is_public": false,
  "user_id": "49366adb-2d13-412f-9ae5-4c35dbffab10",
  "user_name": "johndoe",
  "editor_ids": [
    "49366adb-2d13-412f-9ae5-4c35dbffab10",
    "90ea5cc1-e58c-4c3a-a938-8d9ad7d1bb47"
  ],
  "product_ids": [
    "2bf24db6-0a4f-4b2f-9005-8f4cf66d31ab"
  ],
  "product_slugs": [
    "accessible-keyboard"
  ],
  "created_at": "2026-06-01T20:44:12+00:00",
  "updated_at": "2026-06-01T20:45:01+00:00"
}
```

### Get Authenticated User Collections

```http
GET /api/collections
```

Returns collections owned by the authenticated user.

### Get Public Collections

```http
GET /api/collections/public
GET /api/collections/public?sort_by=created_at
GET /api/collections/public?sort_by=product_count
GET /api/collections/public?sort_by=updated_at
GET /api/collections/public?search=yarn
```

**Query Parameters:**
- `sort_by` (optional): `created_at` (default), `product_count`, or `updated_at`
- `search` (optional): Case-insensitive filter by collection name

### Get Single Collection

```http
GET /api/collections/{collection_slug}
```

`collection_slug` accepts either slug or UUID.

### Create Collection

```http
POST /api/collections
```

**Body:**
```json
{
  "name": "My Favorites",
  "description": "Products I love",
  "is_public": false
}
```

Creator is automatically added to `editor_ids`.

### Create Collection From Search

```http
POST /api/collections/from-search
```

Creates a collection and populates products using product search filters.

### Update Collection

```http
PUT /api/collections/{collection_slug}
```

**Permissions:** Owner or collection editor.

**Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "is_public": true
}
```

### Delete Collection

```http
DELETE /api/collections/{collection_slug}
```

**Permissions:** Owner or collection editor.

Returns `204 No Content`.

### Add Single Product to Collection

```http
POST /api/collections/{collection_slug}/products/{product_slug}
```

**Permissions:** Owner or collection editor.

`product_slug` accepts either slug or UUID.

### Add Multiple Products to Collection

```http
POST /api/collections/{collection_slug}/products
```

**Permissions:** Owner or collection editor.

**Body:**
```json
{
  "product_ids": [
    "accessible-keyboard",
    "2bf24db6-0a4f-4b2f-9005-8f4cf66d31ab"
  ]
}
```

Each entry can be either a product slug or UUID.

### Remove Single Product from Collection

```http
DELETE /api/collections/{collection_slug}/products/{product_slug}
```

**Permissions:** Owner or collection editor.

### Remove All Products from Collection

```http
DELETE /api/collections/{collection_slug}/products
```

**Permissions:** Owner or collection editor.

### Get Collection Editors

```http
GET /api/collections/{collection_slug}/editors
```

For private collections, requires owner/editor access.

**Response:**
```json
{
  "collection_id": "cf4d6c2e-8d8b-4b6e-a0aa-8f07d9a0a1a9",
  "editor_ids": [
    "49366adb-2d13-412f-9ae5-4c35dbffab10",
    "90ea5cc1-e58c-4c3a-a938-8d9ad7d1bb47"
  ]
}
```

### Add Collection Editor

```http
POST /api/collections/{collection_slug}/editors/{editor_user_id}
```

**Permissions:** Collection owner, admin, or moderator.

Returns updated collection object.

### Remove Collection Editor

```http
DELETE /api/collections/{collection_slug}/editors/{editor_user_id}
```

**Permissions:** Collection owner, admin, or moderator.

Returns updated collection object.

**Validation Notes:**
- `editor_user_id` must be a valid UUID.
- Cannot remove the owner as an editor (`400`).

---

## User Requests

### Field Naming Contract (`reason` vs `message`)

- **Canonical field:** `reason`
- **Compatibility alias:** `message` (accepted on create; mirrored from `reason` in responses)
- Clients should migrate to `reason` and treat `message` as deprecated compatibility only.

### Collection Ownership Request Semantics

- Keep `type=collection-ownership` as the request type, but treat it as a **collaborator/editor access request**.
- Approval grants editor access by adding the requester to `collection_editors` / `editor_ids`.
- Approval **does not** transfer literal collection ownership and does not change `collections.user_id`.
- Review uses the existing requests workflow/queue via `PATCH /api/requests/{request_id}`.
- Reviewers for `collection-ownership`: collection owner, admin, or moderator.
- Duplicate pending `collection-ownership` requests for the same `(user_id, collection_id)` are rejected.

### Request Object

```json
{
  "id": "req-1",
  "user_id": "12345",
  "type": "collection-ownership",
  "status": "pending",
  "product_id": null,
  "collection_id": "col-1",
  "reason": "I help maintain this collection",
  "message": "I help maintain this collection",
  "reviewed_by": null,
  "reviewed_at": null,
  "created_at": "2026-06-03T10:00:00+00:00",
  "updated_at": "2026-06-03T10:00:00+00:00"
}
```

### List Requests

```http
GET /api/requests
GET /api/requests?status=pending&type=product-ownership
```

**Permissions:**
- Admin/Moderator: see all requests
- Regular user: sees only own requests

### List My Requests

```http
GET /api/requests/me
GET /api/requests/me?status=pending&type=collection-ownership
```

### Create Request

```http
POST /api/requests/
```

**Supported `type` values:**
- `moderator`
- `admin`
- `product-ownership` (requires `product_id`)
- `source-domain` (requires domain info in `reason`)
- `collection-ownership` (requires `collection_id`; grants editor/collaborator access on approval)

**Example (preferred):**
```json
{
  "type": "collection-ownership",
  "collection_id": "col-1",
  "reason": "I help maintain this collection"
}
```

**Example (legacy compatibility):**
```json
{
  "type": "moderator",
  "message": "I'd like to help moderate"
}
```

### Review Request (Approve/Reject)

```http
PATCH /api/requests/{request_id}
```

**Body:**
```json
{
  "status": "approved"
}
```

**Permissions:**
- Admin/Moderator can review all request types.
- Collection owner can review `collection-ownership` requests for their own collection.
- Only admin can approve `type=admin` role requests.

**Approval effects (collection ownership requests):**
- Approved `type=collection-ownership` requests add the requester to `collection_editors`.
- Ownership does not change; `collections.user_id` remains the existing owner.

### Delete Request

```http
DELETE /api/requests/{request_id}
```

**Permissions:**
- Admin can delete any request.
- Request creator can delete own pending request.

**Response:**
```json
{
  "message": "Request deleted successfully"
}
```

---

## Scraping Logs

### Get Scraping Logs

```http
GET /api/scraping-logs?limit=50
```

**Permissions:** Admin only

**Query Parameters:**
- `limit` (optional): Number of logs to return (default: 50)

**Response:**
```json
[
  {
    "id": "log-1",
    "timestamp": "2026-04-16T12:34:56+00:00",
    "status": "success",
    "totalProductsScraped": 45,
    "productsPerSource": {
      "Thingiverse": 20,
      "Ravelry": 15,
      "GitHub": 10
    },
    "productsAdded": 5,
    "productsUpdated": 10,
    "duration": 12500,
    "errors": []
  }
]
```

### Log Scraping Session

```http
POST /api/scraping-logs
```

**Permissions:** System only

**Body:**
```json
{
  "timestamp": "2026-04-16T12:34:56+00:00",
  "status": "success",
  "totalProductsScraped": 45,
  "productsPerSource": {
    "Thingiverse": 20
  },
  "productsAdded": 5,
  "productsUpdated": 10,
  "duration": 12500,
  "errors": []
}
```

**Response:**
```json
{
  "id": "log-new",
  ...
}
```

---

## Activities

### Log User Activity

```http
POST /api/activities
```

**Body:**
```json
{
  "userId": "12345",
  "type": "product_submit",
  "productId": "prod-1",
  "timestamp": "2026-04-16T12:34:56+00:00",
  "metadata": {
    "action": "edit"
  }
}
```

**Response:**
```json
{
  "success": true
}
```

### Cleanup Old Activities

```http
POST /api/activities/cleanup
```

**Permissions:** Admin only

**Body:**
```json
{
  "daysToKeep": 90
}
```

**Response:**
```json
{
  "success": true
}
```

---

## Rate Limits

Currently, there are no enforced rate limits, but this may change in the future.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `INVALID_PARAMS` | Invalid parameters | Missing or invalid request parameters |
| `NOT_FOUND` | Resource not found | Requested resource doesn't exist |
| `UNAUTHORIZED` | Unauthorized | Sign in required |
| `FORBIDDEN` | Forbidden | Insufficient permissions |
| `DUPLICATE` | Duplicate resource | Resource already exists |
| `VALIDATION_ERROR` | Validation failed | Input validation failed |

---

**Last Updated**: January 2025

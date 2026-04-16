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
    "imageUrl": "data:image/png;base64,...",
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
    "headerImage": "data:image/png;base64,...",
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

### Get All Collections

```http
GET /api/collections
GET /api/collections?public=true
```

**Query Parameters:**
- `public` (optional): Filter public collections only

**Response:**
```json
[
  {
    "id": "coll-1",
    "name": "My Favorites",
    "description": "Products I love",
    "userId": "12345",
    "userName": "johndoe",
    "productIds": ["prod-1", "prod-2"],
    "createdAt": 1704067200000,
    "updatedAt": 1704153600000,
    "isPublic": false
  }
]
```

### Get Single Collection

```http
GET /api/collections/:id
```

**Parameters:**
- `id`: Collection ID

**Response:**
```json
{
  "id": "coll-1",
  "name": "My Favorites",
  ...
}
```

### Get User's Collections

```http
GET /api/users/:userId/collections
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "id": "coll-1",
    "name": "My Favorites",
    "userId": "12345",
    ...
  }
]
```

### Create Collection

```http
POST /api/collections
```

**Body:**
```json
{
  "name": "My Favorites",
  "description": "Products I love",
  "userId": "12345",
  "userName": "johndoe",
  "productIds": [],
  "isPublic": false
}
```

**Response:**
```json
{
  "id": "coll-new",
  "name": "My Favorites",
  "createdAt": 1704153600000,
  "updatedAt": 1704153600000,
  ...
}
```

### Update Collection

```http
PATCH /api/collections/:id
```

**Permissions:** Collection owner only

**Parameters:**
- `id`: Collection ID

**Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "isPublic": true
}
```

**Response:**
```json
{
  "id": "coll-1",
  "name": "Updated Name",
  "updatedAt": 1704153600000,
  ...
}
```

### Delete Collection

```http
DELETE /api/collections/:id
```

**Permissions:** Collection owner only

**Parameters:**
- `id`: Collection ID

**Response:**
```json
{
  "success": true
}
```

### Add Product to Collection

```http
POST /api/collections/:id/products
```

**Permissions:** Collection owner only

**Parameters:**
- `id`: Collection ID

**Body:**
```json
{
  "productId": "prod-1"
}
```

**Response:**
```json
{
  "id": "coll-1",
  "productIds": ["prod-1"],
  "updatedAt": 1704153600000,
  ...
}
```

### Remove Product from Collection

```http
DELETE /api/collections/:id/products/:productId
```

**Permissions:** Collection owner only

**Parameters:**
- `id`: Collection ID
- `productId`: Product ID to remove

**Response:**
```json
{
  "id": "coll-1",
  "productIds": [],
  "updatedAt": 1704153600000,
  ...
}
```

---

## User Requests

### Get All Requests

```http
GET /api/requests
GET /api/requests?status=pending
```

**Query Parameters:**
- `status` (optional): Filter by status (`pending`, `approved`, `rejected`)

**Response:**
```json
[
  {
    "id": "req-1",
    "userId": "12345",
    "userName": "johndoe",
    "userAvatarUrl": "https://...",
    "type": "moderator",
    "message": "I'd like to help moderate",
    "status": "pending",
    "createdAt": 1704067200000
  }
]
```

### Get User's Requests

```http
GET /api/users/:userId/requests
```

**Parameters:**
- `userId`: User ID

**Response:**
```json
[
  {
    "id": "req-1",
    "userId": "12345",
    "type": "moderator",
    "status": "pending",
    ...
  }
]
```

### Create Request

```http
POST /api/requests
```

**Body:**
```json
{
  "userId": "12345",
  "userName": "johndoe",
  "userAvatarUrl": "https://...",
  "type": "moderator",
  "message": "I'd like to help moderate"
}
```

For product management requests:
```json
{
  "userId": "12345",
  "userName": "johndoe",
  "type": "product-ownership",
  "productId": "prod-1",
  "message": "I created this product"
}
```

**Response:**
```json
{
  "id": "req-new",
  "userId": "12345",
  "type": "moderator",
  "status": "pending",
  "createdAt": 1704153600000,
  ...
}
```

### Approve Request

```http
POST /api/requests/:id/approve
```

**Permissions:** Admin only

**Parameters:**
- `id`: Request ID

**Body:**
```json
{
  "reviewerId": "admin-id",
  "note": "Approved - welcome to the team!"
}
```

**Response:**
```json
{
  "id": "req-1",
  "status": "approved",
  "reviewedAt": 1704153600000,
  "reviewedBy": "admin-id",
  "reviewerNote": "Approved - welcome to the team!",
  ...
}
```

### Reject Request

```http
POST /api/requests/:id/reject
```

**Permissions:** Admin only

**Parameters:**
- `id`: Request ID

**Body:**
```json
{
  "reviewerId": "admin-id",
  "note": "Not at this time"
}
```

**Response:**
```json
{
  "id": "req-1",
  "status": "rejected",
  "reviewedAt": 1704153600000,
  "reviewedBy": "admin-id",
  "reviewerNote": "Not at this time",
  ...
}
```

### Withdraw Request

```http
POST /api/requests/:id/withdraw
```

**Permissions:** Request creator only

**Parameters:**
- `id`: Request ID

**Body:**
```json
{
  "userId": "12345"
}
```

**Response:**
```json
{
  "success": true
}
```

### Delete Request

```http
DELETE /api/requests/:id
```

**Permissions:** Admin only

**Parameters:**
- `id`: Request ID

**Response:**
```json
{
  "success": true
}
```

### Cleanup Stale Requests

```http
POST /api/requests/cleanup
```

**Permissions:** Admin only

Removes requests for deleted products and archives old completed requests.

**Response:**
```json
{
  "removedStaleProductRequests": 5,
  "archivedOldRequests": 12,
  "totalRemaining": 3
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

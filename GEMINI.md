# Data Schema

## Tables

### 1. `emails`
Stores information about received email threads.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `thread_id` | `varchar` | NO | Primary Key. Unique identifier for the email thread. |
| `original_received_date` | `timestamptz` | NO | The date when the email was first received. |
| `last_received_date` | `timestamptz` | NO | The date of the most recent activity in the thread. |
| `sender_address` | `text` | NO | Email address of the sender. |
| `cc_address` | `text` | YES | Carbon Copy (CC) email addresses. |
| `title` | `text` | YES | Subject line of the email. |
| `content` | `text` | YES | Body content of the email. |
| `original_pdf_path` | `text` | YES | Path to the originally attached PDF file. |

### 2. `rns`
The main table for tracking Registration Numbers (RN) and their processing status.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `RN` | `varchar` | NO | Primary Key. Unique registration number/record ID. |
| `recent_thread_id` | `varchar` | YES | Foreign Key. Reference to the most recent thread in `emails`. |
| `original_received_date` | `timestamptz` | YES | Initial receipt date of the application. |
| `last_received_date` | `timestamptz` | YES | Most recent update or receipt date. |
| `file_path` | `text` | YES | Path to the processed or finished file. |
| `mail_count` | `integer` | NO | Count of emails associated with this RN (Default: 1). |
| `region` | `text` | YES | Geographical region of the application. |
| `customer` | `text` | YES | Name of the customer/applicant. |
| `model` | `text` | YES | Product or vehicle model name. |
| `special` | `ARRAY` | YES | Array of special notes or category tags. |
| `is_urgent` | `boolean` | YES | Flag indicating if the request is urgent (Default: false). |
| `all_ai` | `boolean` | YES | Flag indicating if the process was fully AI-driven (Default: false). |
| `worker_id` | `integer` | YES | Foreign Key. ID of the assigned worker. |
| `status` | `varchar` | NO | Current processing status (Default: '신규'). |

### 3. `duplicated_rn`
Stores information about duplicate RN entries detected during processing.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `thread_id` | `varchar` | NO | Primary Key. Unique thread identifier for the duplicate record. |
| `RN` | `text` | YES | The duplicated Registration Number. |
| `received_date` | `timestamptz` | YES | Date when the duplicate was received. |
| `file_path` | `text` | YES | Path to the associated file. |
| `region` | `text` | YES | Region associated with the duplicate entry. |

### 4. `chained_emails`
Stores the history of email chains associated with a specific thread.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `history_id` | `integer` | NO | Primary Key. Auto-incrementing identifier for the history record. |
| `thread_id` | `varchar` | NO | Foreign Key. Reference to the parent email thread in `emails`. |
| `received_date` | `timestamptz` | NO | The date when this specific email in the chain was received. |
| `content` | `text` | YES | Body content of the specific email in the chain. |
| `chained_file_path` | `text` | YES | Path to any file attached to this specific email in the chain. |

# Git Commit Message Guidelines

When generating or proposing git commit messages, provide them in **text format** for review, rather than executing them directly via shell immediately (unless explicitly instructed to commit).

## Structure
```
type: Subject

body

footer
```

## Type Keywords
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Formatting, missing semicolons, etc. (no code change)
- `refactor`: Refactoring production code
- `test`: Adding or refactoring tests
- `chore`: Build process, package manager, etc.

## Rules
1. **Always provide a commit message in English at the end of the response if any code changes or file modifications were performed.**
2. **Subject**:
   - Max 50 characters.
   - No period at the end.
   - Imperative mood (e.g., "Add feature" not "Added feature").
   - Capitalized first letter.
3. **Body** (Optional):
   - Wrap at 72 characters.
   - Focus on "What" and "Why", not "How".
4. **Footer** (Optional):
   - Reference issues (e.g., `Resolves: #123`).

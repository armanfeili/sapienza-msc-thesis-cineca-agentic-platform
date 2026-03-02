# Data Retention Policy

## Overview
This document defines our **data retention and deletion policies** in compliance with:
- **GDPR (EU)**
- **CCPA (California)**
- Other applicable privacy and data protection laws

Our goal is to **retain personal and operational data only for as long as necessary** for the purposes for which it was collected, while meeting any legal or contractual obligations.

---

## 1. Retention Principles

1. **Data Minimization** – Store only what is required for business, legal, or regulatory purposes.
2. **Purpose Limitation** – Data is retained only for its intended purpose.
3. **Security** – All retained data is encrypted and access-controlled.
4. **Anonymization** – Where possible, personal data is anonymized instead of deleted to support analytics.

---

## 2. Retention Periods by Data Type

| Data Category                          | Retention Period                         | Notes |
|----------------------------------------|-------------------------------------------|-------|
| **User account information**           | Active + 12 months after closure          | Allows for account reactivation and dispute resolution |
| **Authentication credentials**         | Until account deletion                    | Passwords are stored as salted hashes |
| **User-generated content** (e.g., messages, uploads) | Until deleted by user or account closure  | May be anonymized for analysis |
| **Transaction records**                 | 7 years                                   | Required for tax and audit compliance |
| **Access logs (with IP addresses)**     | 30 days                                   | Then anonymized |
| **Error logs and debug data**           | 90 days                                   | May be retained longer if linked to incident reports |
| **System backups**                      | 90 days                                   | Encrypted at rest and in transit |
| **Analytics data**                      | 24 months                                 | Stored in aggregated/anonymized form |
| **Security incident reports**           | Minimum 3 years                           | To meet compliance and audit requirements |
| **Consent records**                     | Duration of consent + 6 years             | Proof of lawful basis for processing |

---

## 3. Backup Retention

- Daily backups: retained for **30 days**
- Weekly backups: retained for **90 days**
- Backups are **encrypted (AES-256)** and stored in **geographically redundant** locations.
- Backups older than retention limits are **securely destroyed**.

---

## 4. Anonymization & Pseudonymization

To extend data usability without violating privacy laws:
- **Anonymization** – irreversible removal of identifiers.
- **Pseudonymization** – replacement of identifiers with keys stored separately.

Example:  
Instead of retaining `"user_id": 12345`, we may retain `"user_key": "abcXYZ"` in a separate mapping table accessible only to authorized personnel.

---

## 5. Deletion Process

When the retention period expires:
1. Data is **flagged for deletion** by automated scripts.
2. Secure deletion is performed (e.g., cryptographic wiping or overwrite).
3. Deletion events are logged for **audit purposes**.

---

## 6. Exceptions to Standard Retention

We may retain data beyond standard periods if:
- Required by law (e.g., court orders)
- Necessary for ongoing litigation
- Related to unresolved disputes or investigations

---

## 7. User Data Deletion Requests

Under GDPR/CCPA, users can request:
- Complete deletion of their personal data
- Deletion of specific data categories

Requests are processed **within 30 days**, with verification steps to confirm identity.

---

## 8. Review & Compliance

- This policy is reviewed **annually** or when laws/regulations change.
- Compliance audits are conducted at least **once per year**.
- Policy changes are communicated to relevant stakeholders.

---

**Last reviewed:** 2025-08-09

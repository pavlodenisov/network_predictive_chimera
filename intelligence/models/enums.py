"""String-backed enums (spec §4, §7-8). Stored as their ``value`` string — portable
across PostgreSQL and SQLite. Validated at the application layer.
"""

from __future__ import annotations

from enum import StrEnum


class PersonClass(StrEnum):
    FOUNDER = "FOUNDER"
    POTENTIAL_FOUNDER = "POTENTIAL_FOUNDER"
    LP = "LP"
    POTENTIAL_LP = "POTENTIAL_LP"
    INVESTOR = "INVESTOR"
    OPERATOR = "OPERATOR"
    ENGINEER = "ENGINEER"
    RESEARCHER = "RESEARCHER"
    TALENT = "TALENT"
    CONNECTOR = "CONNECTOR"
    PORTFOLIO_EXECUTIVE = "PORTFOLIO_EXECUTIVE"
    UNKNOWN = "UNKNOWN"


class MonitoringStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    REVIEW = "REVIEW"
    ACTIVE_MONITORING = "ACTIVE_MONITORING"
    PASSIVE_MONITORING = "PASSIVE_MONITORING"
    ARCHIVED = "ARCHIVED"
    DISMISSED = "DISMISSED"


class EntityResolutionStatus(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MERGED = "MERGED"


class ResolutionDecision(StrEnum):
    MATCH = "MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


class AliasType(StrEnum):
    NAME = "NAME"
    LINKEDIN_URL = "LINKEDIN_URL"
    GITHUB_USERNAME = "GITHUB_USERNAME"
    PROVIDER_ID = "PROVIDER_ID"
    EMAIL = "EMAIL"
    OTHER = "OTHER"


class OrganizationType(StrEnum):
    STARTUP = "startup"
    PUBLIC_COMPANY = "public_company"
    PRIVATE_COMPANY = "private_company"
    FUND = "fund"
    FUND_OF_FUNDS = "fund_of_funds"
    FAMILY_OFFICE = "family_office"
    ENDOWMENT = "endowment"
    FOUNDATION = "foundation"
    UNIVERSITY = "university"
    RESEARCH_LAB = "research_lab"
    PORTFOLIO_COMPANY = "portfolio_company"
    OTHER = "other"


class Function(StrEnum):
    ENGINEERING = "engineering"
    RESEARCH = "research"
    PRODUCT = "product"
    DESIGN = "design"
    SALES = "sales"
    MARKETING = "marketing"
    OPERATIONS = "operations"
    FINANCE = "finance"
    LEGAL = "legal"
    EXECUTIVE = "executive"
    INVESTING = "investing"
    OTHER = "other"


class Seniority(StrEnum):
    IC = "ic"
    SENIOR_IC = "senior_ic"
    MANAGER = "manager"
    DIRECTOR = "director"
    VP = "vp"
    SVP = "svp"
    C_LEVEL = "c_level"
    FOUNDER = "founder"
    PARTNER = "partner"
    BOARD = "board"
    ADVISOR = "advisor"


SENIORITY_LADDER: dict[str, int] = {
    Seniority.IC: 1,
    Seniority.SENIOR_IC: 2,
    Seniority.MANAGER: 3,
    Seniority.DIRECTOR: 4,
    Seniority.VP: 5,
    Seniority.SVP: 6,
    Seniority.C_LEVEL: 7,
    Seniority.PARTNER: 7,
    Seniority.FOUNDER: 7,
    Seniority.BOARD: 6,
    Seniority.ADVISOR: 3,
}


class SourceType(StrEnum):
    PROFESSIONAL_PROFILE = "professional_profile"
    PROFESSIONAL_ACTIVITY = "professional_activity"
    NEWS = "news"
    RSS = "rss"
    CRM = "crm"
    MANUAL_CSV = "manual_csv"
    JSON_SNAPSHOT = "json_snapshot"
    COMPANY_WEB = "company_web"
    GITHUB = "github"
    PATENTS = "patents"
    ACADEMIC = "academic"
    ENRICHMENT = "enrichment"
    CRUNCHBASE = "crunchbase"
    PITCHBOOK = "pitchbook"
    SYNTHETIC = "synthetic"
    WEB_SEARCH = "web_search"


class ContentType(StrEnum):
    PROFILE_SNAPSHOT = "profile_snapshot"
    ACTIVITY_POST = "activity_post"
    NEWS_ARTICLE = "news_article"
    CSV_ROW = "csv_row"
    JSON_RECORD = "json_record"
    PATENT = "patent"
    PAPER = "paper"
    REPO = "repo"
    MANUAL_NOTE = "manual_note"


class SubjectType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    EMPLOYMENT = "employment"
    RELATIONSHIP = "relationship"


class ExtractionMethod(StrEnum):
    DETERMINISTIC_PARSE = "deterministic_parse"
    SNAPSHOT_DIFF = "snapshot_diff"
    LLM = "llm"
    MANUAL = "manual"
    IMPORT = "import"


class EventStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    EXPIRED = "expired"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RelationshipType(StrEnum):
    CHIMERA_TEAM = "chimera_team"
    COLLEAGUE = "colleague"
    COWORKER_PAST = "coworker_past"
    COINVESTOR = "coinvestor"
    SCHOOL = "school"
    FOUNDER_INVESTOR = "founder_investor"
    INTRODUCED_BY = "introduced_by"
    PERSONAL = "personal"
    UNKNOWN = "unknown"


class RelationshipStrength(StrEnum):
    UNKNOWN = "UNKNOWN"
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    DIRECT = "DIRECT"


class ModelTarget(StrEnum):
    FOUNDER = "founder"
    LP = "lp"
    TALENT = "talent"
    CONNECTOR = "connector"


class ScoringModelStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class RoleNeedStatus(StrEnum):
    OPEN = "open"
    FILLED = "filled"
    PAUSED = "paused"


class WeeklyRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ParseStatus(StrEnum):
    OK = "ok"
    INVALID_RETRIED_OK = "invalid_retried_ok"
    FAILED = "failed"


class SourceHealthStatus(StrEnum):
    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    FAILED = "failed"
    DISABLED = "disabled"


class FeedbackType(StrEnum):
    CONTACT_NOW = "CONTACT_NOW"
    CONSIDER = "CONSIDER"
    PASS = "PASS"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    INCORRECT_EVENT = "INCORRECT_EVENT"
    INCORRECT_IDENTITY = "INCORRECT_IDENTITY"
    IMPORTANT_PERSON = "IMPORTANT_PERSON"
    NOT_RELEVANT = "NOT_RELEVANT"
    INTRO_REQUESTED = "INTRO_REQUESTED"
    INTRO_COMPLETED = "INTRO_COMPLETED"
    CONTACTED = "CONTACTED"
    MEETING_BOOKED = "MEETING_BOOKED"
    INVESTED = "INVESTED"
    HIRED = "HIRED"
    LP_CONVERSATION = "LP_CONVERSATION"
    LP_COMMITMENT = "LP_COMMITMENT"
    VIEWED = "VIEWED"
    SAVED = "SAVED"


class OverrideTargetType(StrEnum):
    EVENT = "event"
    EMPLOYMENT = "employment"
    CLASSIFICATION = "classification"
    RELATIONSHIP = "relationship"
    ENTITY_MERGE = "entity_merge"
    ENTITY_UNMERGE = "entity_unmerge"
    SOURCE_STATE = "source_state"
    PERSON_PIN = "person_pin"
    MANUAL_EVIDENCE = "manual_evidence"


class ActionType(StrEnum):
    CONTACT_NOW = "CONTACT_NOW"
    CONSIDER_CONTACT = "CONSIDER_CONTACT"
    MONITOR = "MONITOR"
    REQUEST_INTRO = "REQUEST_INTRO"
    VERIFY_DATA = "VERIFY_DATA"
    MATCH_TO_PORTFOLIO_ROLE = "MATCH_TO_PORTFOLIO_ROLE"
    LP_RELATIONSHIP_BUILDING = "LP_RELATIONSHIP_BUILDING"
    PASS = "PASS"
    UNKNOWN = "UNKNOWN"


class DecisionSource(StrEnum):
    AUTO = "auto"
    ANALYST = "analyst"

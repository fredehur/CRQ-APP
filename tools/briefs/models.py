from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverMeta(_Strict):
    title: str
    classification: str
    prepared_by: str
    reviewed_by: str
    issued_at: date
    version: str


class BriefData(_Strict):
    """Base marker. Concrete brief types inherit via composition (cover: CoverMeta)."""
    pass


# ---- SHARED LITERALS ----

Severity = Literal["critical", "high", "medium", "monitor"]
Region = Literal["APAC", "AME", "LATAM", "MED", "NCE"]
DriverCategory = Literal["M", "W", "C", "G", "S"]
DeltaDirection = Literal["up", "high", "flat", "down", "cyber"]
LabelPos = Literal["up", "down", "left", "right"]


# ---- BOARD ----

class BoardCover(CoverMeta):
    quarter: str
    quarter_short: str
    board_meeting: str
    distribution_note: str


class PosturePanel(_Strict):
    overall_posture: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    posture_shift: str
    admiralty: str
    admiralty_shift: str
    scenarios_on_watch: int = Field(ge=0)
    scenarios_split: str
    next_review: str


class BoardTakeaway(_Strict):
    n: int = Field(ge=1)
    severity: Severity
    body_markdown: str
    anchor: str


class RegionDelta(_Strict):
    region: Region
    direction: DeltaDirection
    label: str
    cause: str


class KeyDevelopment(_Strict):
    n: int = Field(ge=1)
    category: DriverCategory
    headline: str
    body: str
    meaning: str
    severity: Severity
    region: str
    anchors: list[str]


class AlsoTrackingItem(_Strict):
    head: str
    tail: str


class WatchNextItem(_Strict):
    horizon: str
    head: str
    tail: str


class MatrixDot(_Strict):
    scenario_id: str
    region: Region
    label: str
    likelihood: int = Field(ge=0, le=100)
    impact: int = Field(ge=0, le=100)
    severity: Severity
    label_position: LabelPos


class RegisterRow(_Strict):
    id: str
    region: Region
    headline: str
    severity: Severity


class RiskMatrix(_Strict):
    headline: str
    bottom_line: str
    dots: list[MatrixDot]
    register_tail: list[RegisterRow]


class ScenarioPosture(_Strict):
    pill_label: str
    pill_severity: Severity
    severity: str
    likelihood: str
    admiralty: str
    delta_vs_prior: str


class ScenarioNarrative(_Strict):
    lede: str
    paragraphs: list[str]


class EvidenceRef(_Strict):
    ref: str
    headline: str
    admiralty: str


class BoardScenario(_Strict):
    id: str
    region: str
    title: str
    type_tags: list[str]
    posture: ScenarioPosture
    narrative: ScenarioNarrative
    implications: list[str]
    baselines_moved: list[str]
    drivers: list[str]
    actions: list[str]
    evidence_anchors: list[EvidenceRef]


class ReadingRule(_Strict):
    cond: str
    then_markdown: str


class Methodology(_Strict):
    sources: dict[str, str]
    rating_system: dict[str, str]
    reading_rules: list[ReadingRule]
    against_last_quarter_prose: str
    against_last_quarter_kv: dict[str, str]


class EndMatter(_Strict):
    distribution: dict[str, str]
    provenance: dict[str, str]
    handling_paragraphs: list[str]
    linked_products: dict[str, str]


class BoardBriefData(BriefData):
    cover: BoardCover
    state_of_risk_line: str
    cover_thesis_title: str
    cover_thesis_subtitle: str
    posture: PosturePanel
    board_takeaways: list[BoardTakeaway]
    delta_bar: list[RegionDelta] = Field(min_length=5, max_length=5)
    key_developments: list[KeyDevelopment]
    also_tracking: list[AlsoTrackingItem]
    watch_next: list[WatchNextItem]
    matrix: RiskMatrix
    scenarios: list[BoardScenario]
    methodology: Methodology
    end_matter: EndMatter


# ---- CISO ----

CisoRegionClassification = Literal["moved", "cyber-pressed", "quieted", "baseline"]
CisoDirection = Literal["up", "flat", "down", "cyber"]
DeltaRibbonKind = Literal["moved-up", "moved-new", "moved-down", "no-delta"]


class CisoCover(CoverMeta):
    month: str
    month_short: str
    audience: str


class CisoPosturePanel(_Strict):
    posture: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    posture_shift: str
    admiralty: str
    admiralty_shift: str
    regions_moved: int = Field(ge=0, le=5)
    regions_movement_summary: str
    scenarios_watched: int = Field(ge=0)
    scenarios_delta_note: str


class CisoTakeaway(_Strict):
    n: int
    severity: Literal["cyber", "critical", "high", "medium", "monitor"]
    body_markdown: str
    anchor: str


class RegionCell(_Strict):
    region: Region
    classification: CisoRegionClassification
    direction: CisoDirection
    status_label: str
    admiralty: str
    admiralty_shift: str
    note: str
    why_clear_label: str
    why_clear_body: str


class CrossRegionalItem(_Strict):
    tag: str
    tag_cyber: bool
    head: str
    body: str
    delta: Literal["up", "down", "flat"]
    delta_label: str
    rail_note: str
    anchors: list[str]


class CouplingStrip(_Strict):
    region: Region
    label: str
    physical_track: str
    cyber_track: str
    summary: str


class CyberEntry(_Strict):
    k: str
    ctx: str
    body: str
    impact: str
    severity: Severity
    region_or_scope: str
    admiralty: str
    anchors: list[str]


class CyberSurface(_Strict):
    sector_campaigns: list[CyberEntry]
    actor_activity: list[CyberEntry]
    vulnerability_signal: list[CyberEntry]


class JoinFacts(_Strict):
    title: str
    narrative_paragraphs: list[str]
    facts: dict[str, str]


class TimelineTick(_Strict):
    pct_pos: int = Field(ge=0, le=100)
    label: str


class TimelineEvent(_Strict):
    start_pct: float = Field(ge=0, le=100)
    width_pct: float = Field(ge=0, le=100)
    label: str
    is_ghost: bool = False


class Timeline(_Strict):
    range_label: str
    ticks: list[TimelineTick]
    physical_events: list[TimelineEvent]
    cyber_events: list[TimelineEvent]
    join_marks: list[float]


class CyberPhysicalJoin(_Strict):
    region: Region
    title_markdown: str
    lede: str
    physical: JoinFacts
    cyber: JoinFacts
    timeline: Timeline
    read_summary: str


class DeltaRibbon(_Strict):
    kind: DeltaRibbonKind
    tag: str
    body_markdown: str


class CisoScenario(_Strict):
    id: str
    region: str
    title: str
    posture: ScenarioPosture
    delta_ribbon: DeltaRibbon
    narrative: str
    drivers_line: str
    side: dict[str, str]
    anchors: list[str]


class EvidenceEntry(_Strict):
    ref: str
    headline: str
    source: str
    admiralty: str
    timestamp: str
    why: str


class CisoBriefData(BriefData):
    cover: CisoCover
    cover_thesis_primary: str
    cover_thesis_secondary: str
    state_of_risk_line: str
    posture: CisoPosturePanel
    ciso_takeaways: list[CisoTakeaway]
    regions_grid: list[RegionCell] = Field(min_length=5, max_length=5)
    cross_regional_items: list[CrossRegionalItem]
    coupling_strip: CouplingStrip
    cyber_surface: CyberSurface
    cyber_physical_join: CyberPhysicalJoin
    scenarios: list[CisoScenario]
    evidence_physical: list[EvidenceEntry]
    evidence_cyber: list[EvidenceEntry]


# ---- RSM ----

class Coordinates(_Strict):
    lat: float
    lon: float


class Personnel(_Strict):
    total: int
    expat: int
    contractors: int


class OtStackItem(_Strict):
    vendor: str
    product: str
    version: str


class JoinedEvent(_Strict):
    signal_id: str
    headline: str
    where: str
    when: str
    severity: Severity
    distance_km: float | None
    ref: str
    join_reason: str


class CalendarItem(_Strict):
    label: str
    date_str: str
    horizon_days: int


class CyberCalloutComputed(_Strict):
    cve_or_actor: str
    match_kind: str


class CountryPulse(_Strict):
    country: str
    pulse_label: str
    pulse_severity: Literal["green", "amber", "red"]
    forecast_arrow: str
    note: str


class RankedEvent(_Strict):
    what: str
    where: str
    when: str
    severity_short: str
    severity: Severity
    distance_km: float | None
    nearest_site: str
    ref: str


class CyberStripItem(_Strict):
    kind: Literal["ACTOR", "SECTOR", "CVE"]
    text: str
    ref: str


class BaselineDelta(_Strict):
    country_or_label: str
    note: str


class TocEntry(_Strict):
    group: str
    title: str
    page_ref: str


class SiteBaseline(_Strict):
    pulse_label: str
    pulse_severity: str
    forecast_arrow: str
    days_since_incident: int
    admiralty: str
    host_baseline: str


class RegionalCyberPage(_Strict):
    admiralty: str
    actors_count: int
    cves_on_watch: int
    active_campaigns: int
    standing_notes: str
    sector_signal: list[JoinedEvent]
    actor_activity: list[JoinedEvent]
    geography_overlay: list[JoinedEvent]
    vulnerability_signal: list[JoinedEvent]


class SecondarySite(_Strict):
    name: str
    country: str
    country_lead: str
    pulse_label: str
    pulse_severity: str
    forecast_arrow: str
    events: list[JoinedEvent]


class MinorSiteRow(_Strict):
    name: str
    country_code: str
    pulse_label: str
    pulse_severity: str
    forecast_arrow: str
    delta_count: int
    note: str


class PhysicalEvidence(_Strict):
    ref: str
    headline: str
    source: str
    admiralty: str
    timestamp: str
    why: str


class CyberEvidence(_Strict):
    ref: str
    headline: str
    source: str
    admiralty: str
    timestamp: str
    why: str


class SiteContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Existing flat fields — preserved
    site_id: str
    name: str
    region: Region
    country: str
    lat: float
    lon: float
    poi_radius_km: int
    type: str
    subtype: str | None = None
    shift_pattern: str | None = None
    criticality: Literal["crown_jewel", "major", "standard"]
    personnel_count: int
    expat_count: int
    produces: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    feeds_into: list[str] = Field(default_factory=list)
    customer_dependencies: list[dict] = Field(default_factory=list)
    previous_incidents: list[dict] = Field(default_factory=list)
    notable_dates: list[dict] = Field(default_factory=list)
    site_lead: dict
    duty_officer: dict | None = None
    embassy_contact: dict | None = None

    # New additive fields — RSM brief pipeline
    tier: Literal["crown_jewel", "primary", "secondary", "minor"] | None = None
    criticality_drivers: str = ""
    downstream_dependency: str = ""
    asset_type: Literal[
        "wind_farm", "substation", "ops_center",
        "manufacturing", "office", "port",
    ] | None = None
    sector: int | None = None
    status: Literal["active", "commissioning", "decommissioned", "planned"] = "active"
    seerist_country_code: str | None = None
    contractors_count: int = 0
    country_lead: dict | None = None
    host_country_risk_baseline: Literal["low", "elevated", "high"] = "elevated"
    standing_notes: str = ""
    relevant_seerist_categories: list[str] = Field(default_factory=list)
    threat_actors_of_interest: list[int] = Field(default_factory=list)
    relevant_attack_types: list[int] = Field(default_factory=list)
    ot_stack: list[dict] | None = None
    site_cyber_actors_of_interest: list[int] | None = None

    @computed_field
    @property
    def coordinates(self) -> Coordinates:
        return Coordinates(lat=self.lat, lon=self.lon)

    @computed_field
    @property
    def seerist_poi_radius_km(self) -> int:
        return self.poi_radius_km

    @computed_field
    @property
    def resolved_tier(self) -> Literal["crown_jewel", "primary", "secondary", "minor"]:
        if self.tier:
            return self.tier
        return {
            "crown_jewel": "crown_jewel",
            "major": "primary",
            "standard": "secondary",
        }[self.criticality]

    @computed_field
    @property
    def personnel(self) -> Personnel:
        return Personnel(
            total=self.personnel_count,
            expat=self.expat_count,
            contractors=self.contractors_count,
        )

    @computed_field
    @property
    def resolved_country_lead(self) -> dict:
        return self.country_lead or {**self.site_lead, "email": None}

    @computed_field
    @property
    def last_incident(self) -> dict | None:
        if not self.previous_incidents:
            return None
        return sorted(self.previous_incidents, key=lambda i: i.get("date", ""))[-1]


class SiteComputed(_Strict):
    baseline: SiteBaseline
    proximity_hits: list[JoinedEvent]
    pattern_hits: list[JoinedEvent]
    actor_hits: list[JoinedEvent]
    calendar_ahead: list[CalendarItem]
    cyber_callout_computed: CyberCalloutComputed | None


class SiteNarrative(_Strict):
    standing_notes_synthesis: str | None = None
    pattern_framing: str | None = None
    cyber_callout_text: str | None = None


class SiteBlock(_Strict):
    context: SiteContext
    computed: SiteComputed
    narrative: SiteNarrative


class RsmBriefData(BriefData):
    cover: CoverMeta
    admiralty_physical: str
    admiralty_cyber: str
    headline: str
    baseline_strip: list[CountryPulse]
    top_events: list[RankedEvent]
    cyber_strip: list[CyberStripItem]
    baselines_moved: list[BaselineDelta]
    reading_guide: list[TocEntry]
    sites: list[SiteBlock]
    regional_cyber: RegionalCyberPage
    secondary_sites: list[SecondarySite]
    minor_sites: list[MinorSiteRow]
    evidence_physical: list[PhysicalEvidence]
    evidence_cyber: list[CyberEvidence]


# ---- AGENT I/O ----

class SiteForNarration(_Strict):
    id: str
    name: str
    tier: str
    country: str
    country_lead: dict
    criticality_drivers: str
    standing_notes_static: str
    pulse_label: str
    pulse_severity: str
    forecast_arrow: str
    host_baseline: str
    days_since_incident: int
    proximity_hits: list[JoinedEvent]
    pattern_hits: list[JoinedEvent]
    actor_hits: list[JoinedEvent]
    calendar_ahead: list[CalendarItem]
    cyber_event_to_attach: CyberCalloutComputed | None


class WeeklySynthesisInput(_Strict):
    region: str
    week_of: str
    regional_admiralty_physical: str
    regional_admiralty_cyber: str
    baseline_strip: list[CountryPulse]
    top_events: list[RankedEvent]
    baselines_moved: list[BaselineDelta]
    sites_to_narrate: list[SiteForNarration]
    regional_cyber_context: RegionalCyberPage
    evidence_entries: list[dict]


class SiteNarrativeOut(_Strict):
    site_id: str
    standing_notes_synthesis: str | None = None
    pattern_framing: str | None = None
    cyber_callout_text: str | None = None


class WeeklySynthesisOutput(_Strict):
    headline: str
    sites_narrative: list[SiteNarrativeOut]
    regional_cyber_standing_notes: str | None = None
    evidence_why_lines: dict[str, str]

import type { components } from "./api";

type Schemas = components["schemas"];

export const SCHEMA_VERSION = "1.0";

export type Health = Schemas["Health"];
export type Reading = Schemas["Reading"];
export type Insight = Schemas["Insight"];
export type Event = Schemas["Event"];
export type DeviceStatus = Schemas["DeviceStatus"];
export type Session = Schemas["Session"];
export type Source = Schemas["Source"];
export type LinkStatus = Schemas["LinkStatus"];
export type SocketMessage = Schemas["SocketMessage"];
export type CrewMember = Schemas["CrewMember"];
export type Mission = Schemas["Mission"];
export type ModelRun = Schemas["ModelRun"];
export type Finding = Schemas["Finding"];
export type Alert = Schemas["Alert"];
export type AlertPriority = Schemas["AlertPriority"];
export type AlertReview = Schemas["AlertReview"];
export type AlertReviewRequest = Schemas["AlertReviewRequest"];
export type AlertStatus = Schemas["AlertStatus"];
export type AssessmentFinding = Schemas["AssessmentFinding"];
export type AssessmentSignal = Schemas["AssessmentSignal"];
export type CrewAssessment = Schemas["CrewAssessment"];
export type CrewRole = Schemas["CrewRole"];
export type FindingKind = Schemas["FindingKind"];
export type FindingLabel = Schemas["FindingLabel"];
export type FindingPatch = Schemas["FindingPatch"];
export type Modality = Schemas["Modality"];
export type ReviewStatus = Schemas["ReviewStatus"];

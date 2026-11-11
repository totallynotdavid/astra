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

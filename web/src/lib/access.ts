import type { User, UserRole } from "../data/source";

export const userRoleText: Record<UserRole, string> = {
  admin: "Administración",
  doctor: "Médico",
  astronaut: "Astronauta",
  jury: "Jurado",
};

export function reviewerLabel(user: User): string | null {
  return user.role === "admin" || user.role === "doctor" ? userRoleText[user.role] : null;
}

export function canReplay(user: User, replayOnly: boolean): boolean {
  return replayOnly || user.role === "admin";
}

export function ownProfile(user: User): string | null {
  return user.role === "astronaut" && user.crew_member_id
    ? `#/crew/${encodeURIComponent(user.crew_member_id)}`
    : null;
}

export function canSeeLabs(user: User): boolean {
  return user.role !== "astronaut";
}

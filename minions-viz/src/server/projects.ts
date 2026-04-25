/**
 * Legacy shim — superseded by grus.ts. Aggregates across all Grus.
 */
import { loadGrus, projectDirFor } from "./grus.js";
import type { MosProject } from "../shared/types.js";

export function readProjects(): MosProject[] {
  const all: MosProject[] = [];
  for (const g of loadGrus()) all.push(...g.projects);
  return all;
}

export function getProject(port: number): MosProject | null {
  for (const g of loadGrus()) {
    const p = g.projects.find((pp) => pp.port === port);
    if (p) return p;
  }
  return null;
}

export function projectDir(port: number): string {
  for (const g of loadGrus()) {
    if (g.projects.find((p) => p.port === port)) {
      return projectDirFor(g.rootPath, port);
    }
  }
  return "";
}

export function getMinionsRoot(): string {
  return loadGrus()[0]?.rootPath ?? "";
}

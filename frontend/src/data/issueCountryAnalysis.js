import { api } from './api.js';

export async function loadIssueCountryAnalysis({ issueId, countryCode, asOf }, signal) {
  const data = await api.countryAnalysis(issueId, countryCode, signal, asOf);
  return data.analysis;
}

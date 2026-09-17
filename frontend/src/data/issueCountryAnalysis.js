// UI preview. Replace this loader with the issue/country analysis endpoint when it is ready.
export async function loadIssueCountryAnalysis({ issueId, issueTitle, countryCode, countryName, articleCount }) {
  void issueId;
  void countryCode;
  return {
    preview: true,
    articleCount,
    windowLabel: '최근 24시간',
    headline: `${countryName} 매체가 주목한 관점`,
    summary: `‘${issueTitle}’ 관련 보도에서 사건이 미칠 영향과 앞으로의 대응이 주요 쟁점으로 다뤄집니다. 어떤 보도는 기대되는 변화를, 다른 보도는 남아 있는 불확실성을 강조합니다.`,
    details: [
      '반복해서 등장하는 쟁점과 매체별로 관점이 갈리는 부분을 구분해 보여줍니다.',
      '실제 분석에서는 기사 요약과 논조 점수를 근거로 구체적인 주장과 우려를 정리합니다.',
    ],
    analyzedAt: null,
  };
}

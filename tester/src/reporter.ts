/**
 * Report generation module - aggregates test results into final report.
 */

import {
  TestCaseDefinition,
  TestCaseReport,
  TestReport,
  CategoryReport,
  UnexecutedReason,
  TestResult,
} from "./models";

export interface TestExecutionResult {
  test: TestCaseDefinition;
  report: TestCaseReport;
}

/**
 * Generates a final TestReport from discovered tests and execution results.
 */
export function generateReport(
  discoveredTests: TestCaseDefinition[],
  unexecutedTests: Record<string, UnexecutedReason>,
  executedResults: TestExecutionResult[]
): TestReport {
  // Group results by category
  const resultsByCategory = new Map<string, TestExecutionResult[]>();

  for (const result of executedResults) {
    const category = result.test.category;
    const existing = resultsByCategory.get(category);

    if (existing) {
      existing.push(result);
    } else {
      resultsByCategory.set(category, [result]);
    }
  }

  // Build category reports
  const categoryReports: Record<string, CategoryReport> = {};

  for (const [category, results] of resultsByCategory.entries()) {
    categoryReports[category] = buildCategoryReport(results);
  }

  return new TestReport({
    discovered_test_cases: discoveredTests,
    unexecuted: unexecutedTests,
    results: Object.keys(categoryReports).length > 0 ? categoryReports : null,
  });
}

function buildCategoryReport(results: TestExecutionResult[]): CategoryReport {
  let totalPoints = 0;
  let passedPoints = 0;
  const testResults: Record<string, TestCaseReport> = {};

  for (const result of results) {
    const test = result.test;
    const report = result.report;

    totalPoints += test.points;
    if (report.result === TestResult.PASSED) {
      passedPoints += test.points;
    }

    testResults[test.name] = report;
  }

  return new CategoryReport(totalPoints, passedPoints, testResults);
}

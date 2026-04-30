/**
 * Test filtering module - handles include/exclude logic with regex support.
 */

import { TestCaseDefinition, UnexecutedReason, UnexecutedReasonCode } from "./models";

export interface FilterOptions {
  /** Include tests by name or category (OR logic) */
  include: string[] | null;
  /** Include tests by category only */
  include_category: string[] | null;
  /** Include tests by name only */
  include_test: string[] | null;
  /** Exclude tests by name or category (OR logic) */
  exclude: string[] | null;
  /** Exclude tests by category only */
  exclude_category: string[] | null;
  /** Exclude tests by name only */
  exclude_test: string[] | null;
  /** Whether to treat filter strings as regular expressions */
  regex_filters: boolean;
}

export interface FilterResult {
  /** Tests that passed all filters */
  included: TestCaseDefinition[];
  /** Tests that were filtered out, with reasons */
  excluded: Record<string, UnexecutedReason>;
}

/**
 * Filters tests based on include/exclude criteria.
 * Exclude filters have priority over include filters.
 */
export function filterTests(tests: TestCaseDefinition[], options: FilterOptions): FilterResult {
  const included: TestCaseDefinition[] = [];
  const excluded: Record<string, UnexecutedReason> = {};

  for (const test of tests) {
    if (shouldExclude(test, options)) {
      excluded[test.name] = new UnexecutedReason(
        UnexecutedReasonCode.FILTERED_OUT,
        "Test excluded by filter criteria"
      );
    } else if (shouldInclude(test, options)) {
      included.push(test);
    } else {
      excluded[test.name] = new UnexecutedReason(
        UnexecutedReasonCode.FILTERED_OUT,
        "Test not matched by include filters"
      );
    }
  }

  return { included, excluded };
}

function shouldExclude(test: TestCaseDefinition, options: FilterOptions): boolean {
  // Check exclude filters - any match means exclude
  return (
    matchesAnyFilter(test.name, options.exclude, options.regex_filters) ||
    matchesAnyFilter(test.category, options.exclude, options.regex_filters) ||
    matchesAnyFilter(test.category, options.exclude_category, options.regex_filters) ||
    matchesAnyFilter(test.name, options.exclude_test, options.regex_filters)
  );
}

function shouldInclude(test: TestCaseDefinition, options: FilterOptions): boolean {
  // If no include filters specified, include everything (that wasn't excluded)
  if (!hasAnyIncludeFilters(options)) {
    return true;
  }

  // Check include filters - any match means include
  return (
    matchesAnyFilter(test.name, options.include, options.regex_filters) ||
    matchesAnyFilter(test.category, options.include, options.regex_filters) ||
    matchesAnyFilter(test.category, options.include_category, options.regex_filters) ||
    matchesAnyFilter(test.name, options.include_test, options.regex_filters)
  );
}

function hasAnyIncludeFilters(options: FilterOptions): boolean {
  return (
    (options.include !== null && options.include.length > 0) ||
    (options.include_category !== null && options.include_category.length > 0) ||
    (options.include_test !== null && options.include_test.length > 0)
  );
}

function matchesAnyFilter(value: string, filters: string[] | null, useRegex: boolean): boolean {
  if (filters === null || filters.length === 0) {
    return false;
  }

  for (const filter of filters) {
    if (useRegex) {
      try {
        const regex = new RegExp(filter);
        if (regex.test(value)) {
          return true;
        }
      } catch {
        // Invalid regex - treat as literal string
        if (value === filter) {
          return true;
        }
      }
    } else {
      if (value === filter) {
        return true;
      }
    }
  }

  return false;
}

/**
 * SOLtest format parser - parses .test files into TestCaseDefinition objects.
 */

import { readFileSync } from "fs";
import {
  TestCaseDefinition,
  TestCaseDefinitionFile,
  TestCaseType,
  UnexecutedReason,
  UnexecutedReasonCode,
} from "./models";

export type ParseResult =
  | { success: true; test: TestCaseDefinition }
  | { success: false; reason: UnexecutedReason };

/**
 * Parses a .test file into a TestCaseDefinition.
 * Returns either a successfully parsed test or a reason why it couldn't be parsed.
 */
export function parseTestFile(file: TestCaseDefinitionFile): ParseResult {
  try {
    const content = readFileSync(file.test_source_path, "utf-8");
    return parseTestContent(file, content);
  } catch (error) {
    return {
      success: false,
      reason: new UnexecutedReason(
        UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
        `Failed to read test file: ${error instanceof Error ? error.message : String(error)}`
      ),
    };
  }
}

// eslint-disable-next-line complexity
function parseTestContent(file: TestCaseDefinitionFile, content: string): ParseResult {
  const lines = content.split("\n");

  // Split into metadata and source code sections
  let emptyLineIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]?.trim() === "") {
      emptyLineIndex = i;
      break;
    }
  }

  if (emptyLineIndex === -1) {
    return {
      success: false,
      reason: new UnexecutedReason(
        UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
        "No empty line separating metadata from source code"
      ),
    };
  }

  const metadataLines = lines.slice(0, emptyLineIndex);
  // Source code starts after empty line (not used for parsing)

  // Parse metadata
  let description: string | null = null;
  let category: string | null = null;
  let points = 1;
  const parserExitCodes: number[] = [];
  const interpreterExitCodes: number[] = [];

  for (const line of metadataLines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("***")) {
      description = trimmed.slice(3).trim();
    } else if (trimmed.startsWith("+++")) {
      category = trimmed.slice(3).trim();
    } else if (trimmed.startsWith("!C!")) {
      const code = parseInt(trimmed.slice(3).trim(), 10);
      if (isNaN(code)) {
        return {
          success: false,
          reason: new UnexecutedReason(
            UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
            `Invalid parser exit code: ${trimmed}`
          ),
        };
      }
      parserExitCodes.push(code);
    } else if (trimmed.startsWith("!I!")) {
      const code = parseInt(trimmed.slice(3).trim(), 10);
      if (isNaN(code)) {
        return {
          success: false,
          reason: new UnexecutedReason(
            UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
            `Invalid interpreter exit code: ${trimmed}`
          ),
        };
      }
      interpreterExitCodes.push(code);
    } else if (trimmed.startsWith(">>>")) {
      const p = parseInt(trimmed.slice(3).trim(), 10);
      if (isNaN(p)) {
        return {
          success: false,
          reason: new UnexecutedReason(
            UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
            `Invalid points value: ${trimmed}`
          ),
        };
      }
      points = p;
    }
  }

  // Validate required fields
  if (category === null) {
    return {
      success: false,
      reason: new UnexecutedReason(
        UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
        "Missing required category (+++)"
      ),
    };
  }

  // Determine test type
  const typeResult = determineTestType(parserExitCodes, interpreterExitCodes);
  if (!typeResult.success) {
    return {
      success: false,
      reason: typeResult.reason,
    };
  }

  // Create TestCaseDefinition
  try {
    const test = new TestCaseDefinition({
      name: file.name,
      test_source_path: file.test_source_path,
      stdin_file: file.stdin_file,
      expected_stdout_file: file.expected_stdout_file,
      test_type: typeResult.type,
      description,
      category,
      points,
      expected_parser_exit_codes: parserExitCodes.length > 0 ? parserExitCodes : null,
      expected_interpreter_exit_codes:
        interpreterExitCodes.length > 0 ? interpreterExitCodes : null,
    });

    return { success: true, test };
  } catch (error) {
    return {
      success: false,
      reason: new UnexecutedReason(
        UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
        `Test validation failed: ${error instanceof Error ? error.message : String(error)}`
      ),
    };
  }
}

type TypeResult =
  | { success: true; type: TestCaseType }
  | { success: false; reason: UnexecutedReason };

function determineTestType(parserCodes: number[], interpreterCodes: number[]): TypeResult {
  const hasParser = parserCodes.length > 0;
  const hasInterpreter = interpreterCodes.length > 0;

  // PARSE_ONLY: only parser codes
  if (hasParser && !hasInterpreter) {
    return { success: true, type: TestCaseType.PARSE_ONLY };
  }

  // EXECUTE_ONLY: only interpreter codes
  if (!hasParser && hasInterpreter) {
    return { success: true, type: TestCaseType.EXECUTE_ONLY };
  }

  // COMBINED: both codes present
  if (hasParser && hasInterpreter) {
    // Validate that parser expects success (exit code 0)
    if (parserCodes.length !== 1 || parserCodes[0] !== 0) {
      return {
        success: false,
        reason: new UnexecutedReason(
          UnexecutedReasonCode.CANNOT_DETERMINE_TYPE,
          "Combined tests must have parser exit code = 0"
        ),
      };
    }
    return { success: true, type: TestCaseType.COMBINED };
  }

  // Neither codes present
  return {
    success: false,
    reason: new UnexecutedReason(
      UnexecutedReasonCode.CANNOT_DETERMINE_TYPE,
      "No exit codes specified - cannot determine test type"
    ),
  };
}

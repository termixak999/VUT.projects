/**
 * Test execution module - runs parser and interpreter, compares results.
 */

import { spawn } from "child_process";
import { readFileSync, writeFileSync, unlinkSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import {
  TestCaseDefinition,
  TestCaseReport,
  TestCaseType,
  TestResult,
  UnexecutedReason,
  UnexecutedReasonCode,
} from "./models";

export interface ExecutorOptions {
  /** Path to the sol2xml executable */
  sol2xmlPath: string;
  /** Path to the solint executable */
  solintPath: string;
}

export type ExecutionResult =
  | { success: true; report: TestCaseReport }
  | { success: false; reason: UnexecutedReason };

/**
 * Executes a single test case and returns the result.
 */
export async function executeTest(
  test: TestCaseDefinition,
  options: ExecutorOptions
): Promise<ExecutionResult> {
  try {
    switch (test.test_type) {
      case TestCaseType.PARSE_ONLY:
        return await executeParseOnly(test, options);
      case TestCaseType.EXECUTE_ONLY:
        return await executeExecuteOnly(test, options);
      case TestCaseType.COMBINED:
        return await executeCombined(test, options);
    }
  } catch (error) {
    return {
      success: false,
      reason: new UnexecutedReason(
        UnexecutedReasonCode.OTHER,
        `Unexpected error during execution: ${error instanceof Error ? error.message : String(error)}`
      ),
    };
  }
}

async function executeParseOnly(
  test: TestCaseDefinition,
  options: ExecutorOptions
): Promise<ExecutionResult> {
  // Read and extract SOL source code from test file (skip metadata)
  const content = readFileSync(test.test_source_path, "utf-8");
  const lines = content.split("\n");

  // Find empty line that separates metadata from source code
  let emptyLineIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]?.trim() === "") {
      emptyLineIndex = i;
      break;
    }
  }

  // Extract SOL source (everything after empty line)
  const solSource = lines.slice(emptyLineIndex + 1).join("\n");

  // Create temporary file for SOL
  const tmpFile = join(tmpdir(), `test-${String(Date.now())}-${String(Math.random())}.sol`);
  writeFileSync(tmpFile, solSource);

  try {
    // Run sol2xml with the test file
    const parseResult = await runProcess(options.sol2xmlPath, [tmpFile]);

    if (parseResult.error) {
      return {
        success: false,
        reason: new UnexecutedReason(
          UnexecutedReasonCode.CANNOT_EXECUTE,
          `Failed to run sol2xml: ${parseResult.error}`
        ),
      };
    }

    // Check if exit code matches expectations
    const expectedCodes = test.expected_parser_exit_codes ?? [];
    const result = expectedCodes.includes(parseResult.exitCode)
      ? TestResult.PASSED
      : TestResult.UNEXPECTED_PARSER_EXIT_CODE;

    return {
      success: true,
      report: new TestCaseReport(
        result,
        parseResult.exitCode,
        null,
        parseResult.stdout,
        parseResult.stderr,
        null,
        null,
        null
      ),
    };
  } finally {
    // Clean up temporary file
    try {
      unlinkSync(tmpFile);
    } catch {
      // Ignore cleanup errors
    }
  }
}

async function executeExecuteOnly(
  test: TestCaseDefinition,
  options: ExecutorOptions
): Promise<ExecutionResult> {
  // Read stdin if provided
  const stdin = test.stdin_file ? readFileSync(test.stdin_file, "utf-8") : "";

  // Read and extract XML source code from test file (skip metadata)
  const content = readFileSync(test.test_source_path, "utf-8");
  const lines = content.split("\n");

  // Find empty line that separates metadata from source code
  let emptyLineIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]?.trim() === "") {
      emptyLineIndex = i;
      break;
    }
  }

  // Extract XML (everything after empty line)
  const xmlSource = lines.slice(emptyLineIndex + 1).join("\n");

  // Create temporary file for XML
  const tmpFile = join(tmpdir(), `test-${String(Date.now())}-${String(Math.random())}.xml`);
  writeFileSync(tmpFile, xmlSource);

  try {
    // Run interpreter
    // If stdin is provided, write it to a temporary file and use -i flag
    let stdinFile: string | null = null;
    const solintArgs = ["-s", tmpFile];

    if (stdin) {
      stdinFile = join(tmpdir(), `stdin-${String(Date.now())}-${String(Math.random())}.txt`);
      writeFileSync(stdinFile, stdin);
      solintArgs.push("-i", stdinFile);
    }

    // Run interpreter
    const interpResult = await runProcess(options.solintPath, solintArgs);

    // Clean up stdin temp file
    if (stdinFile) {
      try {
        unlinkSync(stdinFile);
      } catch {
        // Ignore cleanup errors
      }
    }

    if (interpResult.error) {
      return {
        success: false,
        reason: new UnexecutedReason(
          UnexecutedReasonCode.CANNOT_EXECUTE,
          `Failed to run interpreter: ${interpResult.error}`
        ),
      };
    }

    // Check exit code
    const expectedCodes = test.expected_interpreter_exit_codes ?? [];
    if (!expectedCodes.includes(interpResult.exitCode)) {
      return {
        success: true,
        report: new TestCaseReport(
          TestResult.UNEXPECTED_INTERPRETER_EXIT_CODE,
          null,
          interpResult.exitCode,
          null,
          null,
          interpResult.stdout,
          interpResult.stderr,
          null
        ),
      };
    }

    // If exit code is 0 and we have expected output, compare it
    let diffOutput: string | null = null;
    let result = TestResult.PASSED;

    if (interpResult.exitCode === 0 && test.expected_stdout_file) {
      const diffResult = await compareLinesWithDiff(
        interpResult.stdout,
        test.expected_stdout_file
      );

      if (!diffResult.matches) {
        result = TestResult.INTERPRETER_RESULT_DIFFERS;
        diffOutput = diffResult.diffOutput;
      }
    }

    return {
      success: true,
      report: new TestCaseReport(
        result,
        null,
        interpResult.exitCode,
        null,
        null,
        interpResult.stdout,
        interpResult.stderr,
        diffOutput
      ),
    };
  } finally {
    // Clean up temporary file
    try {
      unlinkSync(tmpFile);
    } catch {
      // Ignore cleanup errors
    }
  }
}

// eslint-disable-next-line complexity
async function executeCombined(
  test: TestCaseDefinition,
  options: ExecutorOptions
): Promise<ExecutionResult> {
  // Read and extract SOL source code from test file (skip metadata)
  const content = readFileSync(test.test_source_path, "utf-8");
  const lines = content.split("\n");

  // Find empty line that separates metadata from source code
  let emptyLineIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]?.trim() === "") {
      emptyLineIndex = i;
      break;
    }
  }

  // Extract SOL source (everything after empty line)
  const solSource = lines.slice(emptyLineIndex + 1).join("\n");

  // Create temporary file for SOL
  const tmpSolFile = join(tmpdir(), `test-${String(Date.now())}-${String(Math.random())}.sol`);
  writeFileSync(tmpSolFile, solSource);

  let parseResult;
  try {
    // Run sol2xml first
    parseResult = await runProcess(options.sol2xmlPath, [tmpSolFile]);
  } finally {
    // Clean up SOL temp file
    try {
      unlinkSync(tmpSolFile);
    } catch {
      // Ignore cleanup errors
    }
  }

  if (parseResult.error) {
    return {
      success: false,
      reason: new UnexecutedReason(
        UnexecutedReasonCode.CANNOT_EXECUTE,
        `Failed to run sol2xml: ${parseResult.error}`
      ),
    };
  }

  // Check parser exit code (must be 0 for combined tests)
  if (parseResult.exitCode !== 0) {
    return {
      success: true,
      report: new TestCaseReport(
        TestResult.UNEXPECTED_PARSER_EXIT_CODE,
        parseResult.exitCode,
        null,
        parseResult.stdout,
        parseResult.stderr,
        null,
        null,
        null
      ),
    };
  }

  // Parser succeeded, now run interpreter with the XML output
  const xmlContent = parseResult.stdout;
  const stdin = test.stdin_file ? readFileSync(test.stdin_file, "utf-8") : "";

  // Create temporary file for XML
  const tmpFile = join(tmpdir(), `test-${String(Date.now())}-${String(Math.random())}.xml`);
  writeFileSync(tmpFile, xmlContent);

  try {
    // If stdin is provided, write it to a temporary file and use -i flag
    let stdinFile: string | null = null;
    const solintArgs = ["-s", tmpFile];

    if (stdin) {
      stdinFile = join(tmpdir(), `stdin-${String(Date.now())}-${String(Math.random())}.txt`);
      writeFileSync(stdinFile, stdin);
      solintArgs.push("-i", stdinFile);
    }

    // Run interpreter
    const interpResult = await runProcess(options.solintPath, solintArgs);

    // Clean up stdin temp file
    if (stdinFile) {
      try {
        unlinkSync(stdinFile);
      } catch {
        // Ignore cleanup errors
      }
    }

    if (interpResult.error) {
      return {
        success: false,
        reason: new UnexecutedReason(
          UnexecutedReasonCode.CANNOT_EXECUTE,
          `Failed to run interpreter: ${interpResult.error}`
        ),
      };
    }

    // Check interpreter exit code
    const expectedCodes = test.expected_interpreter_exit_codes ?? [];
    if (!expectedCodes.includes(interpResult.exitCode)) {
      return {
        success: true,
        report: new TestCaseReport(
          TestResult.UNEXPECTED_INTERPRETER_EXIT_CODE,
          parseResult.exitCode,
          interpResult.exitCode,
          parseResult.stdout,
          parseResult.stderr,
          interpResult.stdout,
          interpResult.stderr,
          null
        ),
      };
    }

    // If exit code is 0 and we have expected output, compare it
    let diffOutput: string | null = null;
    let result = TestResult.PASSED;

    if (interpResult.exitCode === 0 && test.expected_stdout_file) {
      const diffResult = await compareLinesWithDiff(
        interpResult.stdout,
        test.expected_stdout_file
      );

      if (!diffResult.matches) {
        result = TestResult.INTERPRETER_RESULT_DIFFERS;
        diffOutput = diffResult.diffOutput;
      }
    }

    return {
      success: true,
      report: new TestCaseReport(
        result,
        parseResult.exitCode,
        interpResult.exitCode,
        parseResult.stdout,
        parseResult.stderr,
        interpResult.stdout,
        interpResult.stderr,
        diffOutput
      ),
    };
  } finally {
    // Clean up temporary file
    try {
      unlinkSync(tmpFile);
    } catch {
      // Ignore cleanup errors
    }
  }
}

interface ProcessResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  error: string | null;
}

function runProcess(command: string, args: string[], stdin?: string): Promise<ProcessResult> {
  return new Promise((resolve) => {
    const proc = spawn(command, args);

    let stdout = "";
    let stderr = "";
    let error: string | null = null;

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    proc.on("error", (err: Error) => {
      error = err.message;
    });

    proc.on("close", (code: number | null) => {
      resolve({
        exitCode: code ?? -1,
        stdout,
        stderr,
        error,
      });
    });

    // Write stdin if provided
    if (stdin !== undefined) {
      proc.stdin.write(stdin);
      proc.stdin.end();
    }
  });
}

interface DiffResult {
  matches: boolean;
  diffOutput: string;
}

async function compareLinesWithDiff(
  actualOutput: string,
  expectedFilePath: string
): Promise<DiffResult> {
  // Create temporary file for actual output
  const tmpFile = join(tmpdir(), `actual-${String(Date.now())}-${String(Math.random())}.txt`);
  writeFileSync(tmpFile, actualOutput);

  try {
    // Run diff
    const diffResult = await runProcess("diff", [tmpFile, expectedFilePath]);

    // diff returns 0 if files are identical, 1 if different
    const matches = diffResult.exitCode === 0;

    return {
      matches,
      diffOutput: diffResult.stdout,
    };
  } finally {
    // Clean up temporary file
    try {
      unlinkSync(tmpFile);
    } catch {
      // Ignore cleanup errors
    }
  }
}

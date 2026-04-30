/**
 * Test discovery module - finds .test files and associated .in/.out files.
 */

import { readdirSync, statSync, existsSync } from "fs";
import { join, basename } from "path";
import { TestCaseDefinitionFile } from "./models";

export interface DiscoveryOptions {
  /** Directory to search for tests */
  directory: string;
  /** Whether to search recursively in subdirectories */
  recursive: boolean;
}

/**
 * Discovers all test case files in the specified directory.
 * For each .test file, looks for associated .in and .out files.
 */
export function discoverTests(options: DiscoveryOptions): TestCaseDefinitionFile[] {
  const testFiles: TestCaseDefinitionFile[] = [];

  function scanDirectory(dir: string): void {
    const entries = readdirSync(dir);

    for (const entry of entries) {
      const fullPath = join(dir, entry);
      const stat = statSync(fullPath);

      if (stat.isDirectory()) {
        if (options.recursive) {
          scanDirectory(fullPath);
        }
      } else if (stat.isFile() && entry.endsWith(".test")) {
        const testFile = createTestCaseFile(fullPath);
        testFiles.push(testFile);
      }
    }
  }

  scanDirectory(options.directory);
  return testFiles;
}

/**
 * Creates a TestCaseDefinitionFile from a .test file path.
 * Checks for associated .in and .out files.
 */
function createTestCaseFile(testPath: string): TestCaseDefinitionFile {
  // Extract test name (filename without .test extension)
  const fileName = basename(testPath);
  const testName = fileName.slice(0, -5); // Remove '.test'

  // Build paths for .in and .out files
  const dirPath = testPath.slice(0, -fileName.length);
  const stdinPath = join(dirPath, `${testName}.in`);
  const stdoutPath = join(dirPath, `${testName}.out`);

  return new TestCaseDefinitionFile({
    name: testName,
    test_source_path: testPath,
    stdin_file: existsSync(stdinPath) ? stdinPath : null,
    expected_stdout_file: existsSync(stdoutPath) ? stdoutPath : null,
  });
}

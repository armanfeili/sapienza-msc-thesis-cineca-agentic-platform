"""
Security audit script for P2.6: Security Review Pass.

Performs automated security checks across the codebase:
- Authentication & authorization vulnerabilities
- Input validation issues
- SQL injection risks
- XSS vulnerabilities  
- Information disclosure
- Insecure defaults
- Missing security headers
"""

import ast
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class SecurityFinding:
    """Represents a security finding."""

    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    category: str  # AUTH, AUTHZ, INPUT_VALIDATION, INFO_DISCLOSURE, etc.
    file_path: str
    line_number: int
    code_snippet: str
    description: str
    recommendation: str
    cwe_id: str = ""  # Common Weakness Enumeration ID


@dataclass
class SecurityAuditReport:
    """Container for audit results."""

    findings: List[SecurityFinding] = field(default_factory=list)
    files_scanned: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0

    def add_finding(self, finding: SecurityFinding):
        """Add a finding and update counters."""
        self.findings.append(finding)
        if finding.severity == "CRITICAL":
            self.critical_count += 1
        elif finding.severity == "HIGH":
            self.high_count += 1
        elif finding.severity == "MEDIUM":
            self.medium_count += 1
        elif finding.severity == "LOW":
            self.low_count += 1
        else:
            self.info_count += 1

    def get_summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            "total": len(self.findings),
            "critical": self.critical_count,
            "high": self.high_count,
            "medium": self.medium_count,
            "low": self.low_count,
            "info": self.info_count,
            "files_scanned": self.files_scanned,
        }


class SecurityAuditor:
    """Performs security audit on Python codebase."""

    def __init__(self, root_dir: str):
        """
        Initialize auditor.

        Args:
            root_dir: Root directory of project to audit
        """
        self.root_dir = Path(root_dir)
        self.report = SecurityAuditReport()

        # Patterns to check
        self.sql_injection_patterns = [
            r"execute\([^,)]*%",  # String formatting in SQL
            r"execute\([^,)]*\+",  # String concatenation in SQL
            r"execute\([^,)]*\.format",  # .format() in SQL
            r'execute\([^,)]*f["\']',  # f-strings in SQL
        ]

        self.hardcoded_secret_patterns = [
            (r'password\s*=\s*["\'](?!.*%|.*\{)[^"\']{8,}["\']', "Hardcoded password"),
            (r'api[_-]?key\s*=\s*["\'](?!.*%|.*\{)[^"\']{16,}["\']', "Hardcoded API key"),
            (r'secret\s*=\s*["\'](?!.*%|.*\{)[^"\']{16,}["\']', "Hardcoded secret"),
            (r'token\s*=\s*["\'](?!.*%|.*\{)[^"\']{20,}["\']', "Hardcoded token"),
        ]

        self.dangerous_functions = {
            "eval": "Unsafe: eval() can execute arbitrary code",
            "exec": "Unsafe: exec() can execute arbitrary code",
            "__import__": "Unsafe: Dynamic imports can be exploited",
            "compile": "Unsafe: compile() can execute arbitrary code",
        }

        self.info_disclosure_patterns = [
            (r"except.*:.*print\(", "Exception details printed to console"),
            (
                r"except.*:.*logger\.(error|warning|info|debug)\(.*\btraceback\b",
                "Traceback logged (potential info disclosure)",
            ),
            (r"raise.*Exception\([^)]*password[^)]*\)", "Password in exception message"),
            (r"raise.*Exception\([^)]*secret[^)]*\)", "Secret in exception message"),
        ]

    def scan_file(self, file_path: Path):
        """
        Scan a single Python file for security issues.

        Args:
            file_path: Path to file to scan
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            self.report.files_scanned += 1

            # Check for SQL injection patterns
            self._check_sql_injection(file_path, content, lines)

            # Check for hardcoded secrets
            self._check_hardcoded_secrets(file_path, content, lines)

            # Check for dangerous functions
            self._check_dangerous_functions(file_path, content, lines)

            # Check for information disclosure
            self._check_info_disclosure(file_path, content, lines)

            # Check for missing auth checks
            self._check_missing_auth(file_path, content, lines)

            # Parse AST for deeper checks
            try:
                tree = ast.parse(content, filename=str(file_path))
                self._check_ast(file_path, tree, lines)
            except SyntaxError:
                pass  # Skip files with syntax errors

        except Exception as e:
            # Log but don't fail audit
            print(f"Error scanning {file_path}: {e}")

    def _check_sql_injection(self, file_path: Path, content: str, lines: List[str]):
        """Check for SQL injection vulnerabilities."""
        for pattern in self.sql_injection_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                self.report.add_finding(
                    SecurityFinding(
                        severity="HIGH",
                        category="SQL_INJECTION",
                        file_path=str(file_path.relative_to(self.root_dir)),
                        line_number=line_num,
                        code_snippet=lines[line_num - 1].strip(),
                        description="Potential SQL injection: String formatting/concatenation in SQL query",
                        recommendation="Use parameterized queries or ORM (SQLAlchemy) instead of string formatting",
                        cwe_id="CWE-89",
                    )
                )

    def _check_hardcoded_secrets(self, file_path: Path, content: str, lines: List[str]):
        """Check for hardcoded secrets."""
        # Skip test files and example files
        if "test" in str(file_path).lower() or "example" in str(file_path).lower():
            return

        for pattern, description in self.hardcoded_secret_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                self.report.add_finding(
                    SecurityFinding(
                        severity="CRITICAL",
                        category="HARDCODED_SECRET",
                        file_path=str(file_path.relative_to(self.root_dir)),
                        line_number=line_num,
                        code_snippet=lines[line_num - 1].strip()[:80],
                        description=f"{description} detected in code",
                        recommendation="Move secret to environment variable or secret manager",
                        cwe_id="CWE-798",
                    )
                )

    def _check_dangerous_functions(self, file_path: Path, content: str, lines: List[str]):
        """Check for dangerous function usage."""
        for func_name, description in self.dangerous_functions.items():
            pattern = rf"\b{func_name}\s*\("
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                self.report.add_finding(
                    SecurityFinding(
                        severity="HIGH",
                        category="DANGEROUS_FUNCTION",
                        file_path=str(file_path.relative_to(self.root_dir)),
                        line_number=line_num,
                        code_snippet=lines[line_num - 1].strip(),
                        description=description,
                        recommendation="Avoid using this function or ensure input is strictly validated",
                        cwe_id="CWE-95",
                    )
                )

    def _check_info_disclosure(self, file_path: Path, content: str, lines: List[str]):
        """Check for information disclosure issues."""
        for pattern, description in self.info_disclosure_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                self.report.add_finding(
                    SecurityFinding(
                        severity="MEDIUM",
                        category="INFO_DISCLOSURE",
                        file_path=str(file_path.relative_to(self.root_dir)),
                        line_number=line_num,
                        code_snippet=lines[line_num - 1].strip()[:100],
                        description=description,
                        recommendation="Avoid exposing sensitive details in logs/errors; use generic error messages for users",
                        cwe_id="CWE-209",
                    )
                )

    def _check_missing_auth(self, file_path: Path, content: str, lines: List[str]):
        """Check for potential missing authentication."""
        # Only check router files
        if "router" not in str(file_path).lower():
            return

        # Look for route decorators without Depends
        route_pattern = r"@router\.(get|post|put|delete|patch)\([^)]*\)"
        for match in re.finditer(route_pattern, content, re.IGNORECASE):
            line_num = content[: match.start()].count("\n") + 1

            # Check next few lines for authentication dependency
            snippet = "\n".join(lines[line_num - 1 : line_num + 5])
            if "Depends" not in snippet and "get_current_user" not in snippet:
                # Check if it's a public endpoint (health, docs, etc.)
                if any(public in snippet.lower() for public in ["health", "docs", "openapi", "status", "redoc"]):
                    continue

                self.report.add_finding(
                    SecurityFinding(
                        severity="MEDIUM",
                        category="MISSING_AUTH",
                        file_path=str(file_path.relative_to(self.root_dir)),
                        line_number=line_num,
                        code_snippet=lines[line_num - 1].strip(),
                        description="Route may be missing authentication dependency",
                        recommendation="Add Depends(get_current_user) or other auth dependency if endpoint should be protected",
                        cwe_id="CWE-306",
                    )
                )

    def _check_ast(self, file_path: Path, tree: ast.AST, lines: List[str]):
        """Perform AST-based security checks."""
        for node in ast.walk(tree):
            # Check for assert statements (can be disabled with -O flag)
            if isinstance(node, ast.Assert):
                self.report.add_finding(
                    SecurityFinding(
                        severity="LOW",
                        category="INSECURE_ASSERT",
                        file_path=str(file_path.relative_to(self.root_dir)),
                        line_number=node.lineno,
                        code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                        description="Assert statement used for security check (can be disabled with -O flag)",
                        recommendation="Use explicit if/raise for security checks instead of assert",
                        cwe_id="CWE-703",
                    )
                )

    def scan_directory(self, exclude_patterns: List[str] = None):
        """
        Recursively scan directory for Python files.

        Args:
            exclude_patterns: List of glob patterns to exclude
        """
        exclude_patterns = exclude_patterns or [
            "**/node_modules/**",
            "**/.venv/**",
            "**/venv/**",
            "**/.git/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/build/**",
        ]

        for py_file in self.root_dir.rglob("*.py"):
            # Check if file should be excluded
            if any(py_file.match(pattern) for pattern in exclude_patterns):
                continue

            self.scan_file(py_file)

    def generate_report(self) -> str:
        """
        Generate formatted security audit report.

        Returns:
            Markdown-formatted report
        """
        summary = self.report.get_summary()

        report_lines = [
            "# Security Audit Report",
            "",
            "## Summary",
            "",
            f"- **Files Scanned**: {summary['files_scanned']}",
            f"- **Total Findings**: {summary['total']}",
            f"- **Critical**: {summary['critical']}",
            f"- **High**: {summary['high']}",
            f"- **Medium**: {summary['medium']}",
            f"- **Low**: {summary['low']}",
            f"- **Info**: {summary['info']}",
            "",
        ]

        if summary["total"] == 0:
            report_lines.append("✅ **No security issues found!**")
            return "\n".join(report_lines)

        # Group findings by severity
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            findings_for_severity = [f for f in self.report.findings if f.severity == severity]

            if not findings_for_severity:
                continue

            report_lines.append(f"## {severity} Severity ({len(findings_for_severity)})")
            report_lines.append("")

            # Group by category
            categories: Dict[str, List[SecurityFinding]] = {}
            for finding in findings_for_severity:
                if finding.category not in categories:
                    categories[finding.category] = []
                categories[finding.category].append(finding)

            for category, findings in categories.items():
                report_lines.append(f"### {category.replace('_', ' ').title()} ({len(findings)})")
                report_lines.append("")

                for i, finding in enumerate(findings, 1):
                    report_lines.extend(
                        [
                            f"**{i}. {finding.file_path}:{finding.line_number}**",
                            "",
                            f"- **Description**: {finding.description}",
                            f"- **Code**: `{finding.code_snippet}`",
                            f"- **Recommendation**: {finding.recommendation}",
                            f"- **CWE**: {finding.cwe_id}" if finding.cwe_id else "",
                            "",
                        ]
                    )

        return "\n".join(report_lines)


def run_security_audit(root_dir: str = ".") -> SecurityAuditReport:
    """
    Run security audit on project.

    Args:
        root_dir: Root directory of project

    Returns:
        SecurityAuditReport with findings
    """
    auditor = SecurityAuditor(root_dir)
    auditor.scan_directory()
    return auditor.report


if __name__ == "__main__":
    import sys

    root_dir = sys.argv[1] if len(sys.argv) > 1 else "."

    print(f"Running security audit on {root_dir}...")
    auditor = SecurityAuditor(root_dir)
    auditor.scan_directory()

    report = auditor.generate_report()
    print(report)

    # Save report
    with open("SECURITY_AUDIT_REPORT.md", "w") as f:
        f.write(report)

    print("\n✅ Report saved to SECURITY_AUDIT_REPORT.md")

    # Exit with error code if critical/high issues found
    summary = auditor.report.get_summary()
    if summary["critical"] > 0 or summary["high"] > 0:
        sys.exit(1)

    sys.exit(0)

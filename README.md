# atlassian-tmp-bridge

Jira Cloud MCP server. Issues, comments, attachments, transitions, bulk operations. Clone/build/install 없이 `uvx`로 바로 실행 가능.

## Why?

[공식 Atlassian MCP 서버](https://github.com/atlassian/atlassian-mcp-server)는 이슈 조회와 검색은 가능하지만, 첨부파일 다운로드([#15](https://github.com/atlassian/atlassian-mcp-server/issues/15)), 이슈 생성/수정/삭제, 상태 전환, 벌크 작업 등 **쓰기 작업이 제한적**입니다. 이 서버는 해당 기능들을 보완합니다.

## Requirements

- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Jira Cloud API token ([생성 페이지](https://id.atlassian.com/manage-profile/security/api-tokens))

## Setup

### Claude Code

```bash
claude mcp add jira-bridge \
  -e JIRA_DOMAIN=your-org.atlassian.net \
  -e JIRA_EMAIL=your@email.com \
  -e JIRA_API_TOKEN=your_token \
  -- uvx --from git+https://github.com/Bldg-7/atlassian-tmp-bridge serve
```

### Manual (mcp.json)

```json
{
  "mcpServers": {
    "jira-bridge": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Bldg-7/atlassian-tmp-bridge", "serve"],
      "env": {
        "JIRA_DOMAIN": "your-org.atlassian.net",
        "JIRA_EMAIL": "your@email.com",
        "JIRA_API_TOKEN": "your_token"
      }
    }
  }
}
```

## Tools

### Issues

| Tool | Description |
|------|-------------|
| `get_issue` | 이슈 상세 조회 (summary, status, assignee, description 등) |
| `search_issues` | JQL로 이슈 검색 (페이지네이션 지원) |
| `count_issues` | JQL 쿼리 매칭 이슈 수 조회 |
| `create_issue` | 이슈 생성 |
| `update_issue` | 이슈 필드 수정 |
| `delete_issue` | 이슈 삭제 |

### Comments

| Tool | Description |
|------|-------------|
| `get_comments` | 이슈의 댓글 목록 조회 |
| `add_comment` | 댓글 추가 |
| `update_comment` | 댓글 수정 |
| `delete_comment` | 댓글 삭제 |

### Attachments

| Tool | Description |
|------|-------------|
| `list_attachments` | 이슈의 첨부파일 목록 조회 |
| `download_attachment` | 첨부파일 다운로드 (base64 이미지로 반환) |
| `upload_attachment` | 파일을 이슈에 첨부 |

### Transitions

| Tool | Description |
|------|-------------|
| `get_transitions` | 이슈의 가능한 상태 전환 목록 조회 |
| `transition_issue` | 이슈 상태 전환 (코멘트 첨부 가능) |

### Bulk Operations

| Tool | Description |
|------|-------------|
| `bulk_create_issues` | 이슈 일괄 생성 (최대 50개) |
| `bulk_update_issues` | 이슈 일괄 수정 (최대 1000개, priority/labels/description) |

## Authentication

Jira Cloud의 [개인 API Token](https://id.atlassian.com/manage-profile/security/api-tokens)을 사용합니다. Basic Auth (`email:api_token`)로 인증하며, OAuth와 달리 토큰 만료/재인증 문제가 없습니다.

필요 권한: 해당 프로젝트의 **Browse projects** 권한 (조회), **Edit issues** 권한 (수정/생성) 등 작업에 맞는 프로젝트 권한이 필요합니다.

## License

MIT

# atlassian-tmp-bridge

Jira attachment download MCP server. Clone/build/install 없이 `uvx`로 바로 실행 가능.

## Why?

[공식 Atlassian MCP 서버](https://github.com/atlassian/atlassian-mcp-server)는 Jira 이슈의 첨부파일 메타데이터는 조회할 수 있지만, **실제 파일을 다운로드하는 tool이 없습니다** ([#15](https://github.com/atlassian/atlassian-mcp-server/issues/15)). 이 서버는 해당 기능을 보완합니다.

## Requirements

- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Jira Cloud API token ([생성 페이지](https://id.atlassian.com/manage-profile/security/api-tokens))

## Setup

### Claude Code

```bash
claude mcp add jira-attachments \
  -e JIRA_DOMAIN=your-org.atlassian.net \
  -e JIRA_EMAIL=your@email.com \
  -e JIRA_API_TOKEN=your_token \
  -- uvx --from git+https://github.com/Bldg-7/atlassian-tmp-bridge serve
```

### Manual (mcp.json)

```json
{
  "mcpServers": {
    "jira-attachments": {
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

### `list_attachments`

Jira 이슈에 첨부된 파일 목록을 조회합니다.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `issue_key` | string | Yes | Jira 이슈 키 (e.g. `PROJ-123`) |

**Returns**: 첨부파일 목록 (ID, 파일명, MIME type, 크기)

```
Attachments on PROJ-123:

- [10001] screenshot.png (image/png, 245760 bytes)
- [10002] spec.pdf (application/pdf, 1048576 bytes)
```

### `download_attachment`

첨부파일을 다운로드하여 base64 인코딩된 이미지로 반환합니다.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `attachment_id` | string | Yes | `list_attachments`에서 조회한 첨부파일 ID |

**Returns**: base64 이미지 (실제 MIME type 반영)

## Usage Flow

```
1. list_attachments("PROJ-123")    → 첨부파일 목록 확인
2. download_attachment("10001")     → 이미지 다운로드
```

## Authentication

Jira Cloud의 [개인 API Token](https://id.atlassian.com/manage-profile/security/api-tokens)을 사용합니다. Basic Auth (`email:api_token`)로 인증하며, OAuth와 달리 토큰 만료/재인증 문제가 없습니다.

필요 권한: 해당 프로젝트의 **Browse projects** 권한만 있으면 됩니다.

## With Official Atlassian MCP

공식 MCP 서버와 병행하여 사용할 수 있습니다:

- 이슈 조회, 검색, 코멘트 등 -> 공식 Atlassian MCP
- 첨부파일 다운로드 -> 이 서버

## License

MIT

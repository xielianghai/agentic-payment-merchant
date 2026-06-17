import { Typography } from 'antd'

export function JsonPreview({ value }: { value: unknown }) {
  return (
    <Typography.Paragraph copyable style={{ marginBottom: 0 }}>
      <pre className="json-preview">{JSON.stringify(value ?? {}, null, 2)}</pre>
    </Typography.Paragraph>
  )
}

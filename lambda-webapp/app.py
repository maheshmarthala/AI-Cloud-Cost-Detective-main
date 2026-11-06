import json

def lambda_handler(event, context):
    # Detect query parameter or default to 'Cloud Explorer'
    params = event.get('queryStringParameters') or {}
    name = params.get('name', 'Cloud Explorer')

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>My Serverless Web App</title>
    <style>
        body {{ 
            font-family: system-ui, -apple-system, sans-serif; 
            background: #0f172a; 
            color: #f8fafc; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            height: 100vh; 
            margin: 0; 
        }}
        .card {{ 
            background: #1e293b; 
            padding: 2.5rem; 
            border-radius: 16px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); 
            text-align: center; 
            max-width: 440px; 
            border: 1px solid #334155;
        }}
        h1 {{ 
            color: #38bdf8; 
            margin: 0.8rem 0; 
            font-size: 1.8rem;
        }}
        p {{ 
            color: #94a3b8; 
            line-height: 1.6; 
        }}
        .badge {{ 
            background: #0369a1; 
            color: #e0f2fe; 
            padding: 5px 14px; 
            border-radius: 20px; 
            font-size: 0.85rem; 
            font-weight: 600; 
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        code {{
            background: #0c1220;
            padding: 2px 6px;
            border-radius: 4px;
            color: #86e8cb;
        }}
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">AWS Lambda Serverless</span>
        <h1>Hello, {name}!</h1>
        <p>This web page was generated dynamically on-demand using <strong>AWS Lambda</strong> with <strong>zero dedicated servers</strong>.</p>
        <p><small>Query string test: Add <code>?name=YourName</code> to the URL.</small></p>
    </div>
</body>
</html>"""

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html; charset=utf-8"
        },
        "body": html_content
    }

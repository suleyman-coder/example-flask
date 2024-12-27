import subprocess
from flask import Flask, request, jsonify, render_template_string, session
import logging
import concurrent.futures
import os
import logging.handlers
import queue

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Session için secret key gerekli

# Loglama ayarları - QueueHandler kullanımı
log_queue = queue.Queue(-1)
queue_handler = logging.handlers.QueueHandler(log_queue)
queue_listener = logging.handlers.QueueListener(log_queue, logging.handlers.RotatingFileHandler('console_app.log', maxBytes=10 * 1024 * 1024, backupCount=5), respect_handler_level=True)
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.addHandler(queue_handler)
queue_listener.start()

executor = concurrent.futures.ProcessPoolExecutor(max_workers=10)

def run_command(command, current_directory):
    try:
        os.chdir(current_directory)
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        error = result.stderr.strip()
        if error:
            output += f"\nError: {error}"
        return output
    except FileNotFoundError:
        return f"Error: Directory '{current_directory}' not found."
    except NotADirectoryError:
        return f"Error: '{current_directory}' is not a directory."
    except PermissionError:
        return f"Error: Permission denied to access '{current_directory}'."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"


@app.route('/console/<int:console_id>', methods=['GET', 'POST'])
def console(console_id):
    if 'current_directory' not in session:
        session['current_directory'] = os.getcwd()
        session['command_history'] = []

    if request.method == 'POST':
        data = request.get_json()
        command = data.get('command', '')
        session['command_history'].append(command)

        future = executor.submit(run_command, command, session['current_directory'])
        try:
            output = future.result()
            if command.lower().startswith("cd"):
                try:
                    new_dir = command.split()[1]
                    new_path = os.path.abspath(os.path.join(session['current_directory'], new_dir))
                    if os.path.isdir(new_path):
                        session['current_directory'] = new_path
                        output += f"\nCurrent directory changed to: {session['current_directory']}"
                    else:
                        output += f"\nError: Directory '{new_dir}' not found."
                except IndexError:
                    output += f"\nUsage: cd <directory>"
                except Exception as e:
                    output += f"\nError changing directory: {str(e)}"
            return jsonify({'output': output})
        except Exception as e:
            logging.exception(f"Console {console_id}: An error occurred processing command '{command}': {e}")
            return jsonify({'output': f"An unexpected error occurred: {str(e)}"})

    return render_template_string(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PyHosting Ultra Console</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Courier New', Courier, monospace;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                overflow: hidden;
            }}
            .terminal-wrapper {{
                width: 100%;
                height: 100%;
                display: flex;
                flex-direction: column;
            }}
            .banner {{
                background-color: #000000;
                color: #00ccff;
                text-align: center;
                padding: 10px;
                font-size: 18px;
                font-weight: bold;
                border-bottom: 2px solid #00ccff;
            }}
            .terminal {{
                flex-grow: 1;
                background-color: #000000;
                display: flex;
                flex-direction: column;
                padding: 10px;
                box-sizing: border-box;
                overflow: hidden;
            }}
            .output {{
                flex-grow: 1;
                overflow-y: auto;
                white-space: pre-wrap;
                color: #00ff00;
                font-size: 14px;
                margin-bottom: 10px;
            }}
            .input-wrapper {{
                display: flex;
                background-color: #111111;
                padding: 10px;
                border-top: 2px solid #333333;
            }}
            .input {{
                flex-grow: 1;
                background: none;
                border: none;
                color: #00ff00;
                font-size: 16px;
                outline: none;
                font-family: 'Courier New', Courier, monospace;
            }}
            .input::placeholder {{
                color: #555555;
            }}
        </style>
    </head>
    <body>
        <div class="terminal-wrapper">
            <div class="banner">PyHosting Ultra</div>
            <div class="terminal" onclick="focusInput()">
                <div class="output" id="output"></div>
                <div class="input-wrapper">
                    <input type="text" class="input" id="command" placeholder="Type a command and press Enter" onkeydown="handleInput(event)" autofocus />
                </div>
            </div>
        </div>
        <script>
            function focusInput() {{
                document.getElementById('command').focus();
            }}

            async function handleInput(event) {{
                if (event.key === 'Enter') {{
                    const command = event.target.value.trim();
                    if (!command) return;

                    const output = document.getElementById('output');
                    output.innerHTML += "\\n> " + command;

                    try {{
                        const response = await fetch('/console/{console_id}', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json'
                            }},
                            body: JSON.stringify({{ command }})
                        }});
                        const data = await response.json();
                        output.innerHTML += "\\n" + data.output;
                    }} catch (error) {{
                        output.innerHTML += "\\nError: Unable to process the command.";
                    }}

                    output.scrollTop = output.scrollHeight;
                    event.target.value = '';
                }}
            }}
        </script>
    </body>
    </html>
    """)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)

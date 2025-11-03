import { useState } from 'react'
import './App.css'
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import json from 'react-syntax-highlighter/dist/esm/languages/hljs/json';
import style from 'react-syntax-highlighter/dist/esm/styles/hljs/a11y-dark';
SyntaxHighlighter.registerLanguage('json', json);
interface Result {
  code: string;
}

function App() {
  const [loading, setLoading] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch('http://localhost:8080/api/process/' + textInput, {
        method: 'GET',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      if (err instanceof Error) {
        setError(`API Error: ${err.message}`);
      } else {
        setError(err as string);
      }
      console.error('Error calling API:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <header>
        <h1>Dibbs Text to Code</h1>
      </header>

      <main>
        <section>
          <p>Click the button below to retrieve data from the API.</p>
          <form>
            <div>
              <label htmlFor="textInput">Text Input:</label>
              <input
                type="text"
                id="textInput"
                name="textInput"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)} />
            </div>
            <button
              type="button"
              id="fetchDataBtn"
              onClick={handleSubmit}
              disabled={loading}>
              {loading ? <div>Waiting for results... <span className='spinner'>⚙</span></div> : "Get data"}
            </button>
          </form>
        </section>

        <section aria-live="polite" aria-label="Data output">
          <h2>Output</h2>
          {error ? error : ""}
          <output id="dataOutput" htmlFor="fetchDataBtn" style={{
            textAlign: "left",
            display: "block",
          }}>
            {result ? (
              <SyntaxHighlighter language='json' style={style}>
                {JSON.stringify(result, null, 2)}
              </SyntaxHighlighter>
            ) : (
              "No data yet. Click the button to retrieve data."
            )}
          </output>
        </section>
      </main>
    </>
  )
}

export default App

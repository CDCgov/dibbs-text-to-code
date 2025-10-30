import { FormGroup, Label, Textarea } from "@trussworks/react-uswds";
import { Layout } from "./components/Layout";
import { useState } from "react";
import { Button } from "./components/Button";
import { Title } from "./components/Title";


function App() {
  const [textInput, setTextInput] = useState("");
  const maxInputLength = 200;

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTextInput(event.target.value);
  }

  return (
    <Layout>
      <div className="flex justify-center">
        <div className="max-w-320">
          <Title className="pt-10">Welcome to Text to Code!</Title>
          <p className="mt-2">The Text-to-Code project introduces a shared service integrated with the AIMS pipeline that can automatically map unstructured or local-coded fields in eICRs to standard codes (e.g. LOINC, SNOMED CT).</p>
          <div className="mt-10">
            <h2 className="">Convert your text for one code at a time</h2>
            <div className="bg-blue-cool-5 max-w-100 rounded-lg p-8 mt-8">
              <FormGroup className="!mt-0">
                <Label htmlFor="text-input">
                  <span className="text-lg font-bold">Nonstandard text input</span>
                </Label>
                <div>
                  <Textarea
                    className="bg-gray-100"
                    id="text-input"
                    name="text-input"
                    placeholder="Measles genotype A probe"
                    maxLength={maxInputLength}
                    value={textInput}
                    onChange={handleChange}>
                  </Textarea>
                  <span className="flow-root w-full text-right font-extralight" >
                    {textInput.length}/{maxInputLength} characters
                  </span>
                </div>
                <div className="mt-4">
                  <Button>
                    Submit
                  </Button>
                  <strong className="ml-4 !font-light">Note: Do not input PII/PHI</strong>
                </div>
              </FormGroup>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}

export default App;

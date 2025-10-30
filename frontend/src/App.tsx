import { CharacterCount, Form, FormGroup, Icon, Label } from "@trussworks/react-uswds";
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
            <h2 className="mt-10">Convert your text for one code at a time</h2>
          <div className="flex justify-around">
            <div className="bg-blue-cool-5 max-w-100 rounded-lg p-8 mt-4">
              <Form onSubmit={""}>
                <FormGroup className="!mt-0">
                  <Label htmlFor="text-input">
                    <span className="text-lg font-bold">Nonstandard text input</span>
                  </Label>
                  <div>
                    <CharacterCount
                      className="bg-gray-100"
                      id="text-input"
                      name="text-input"
                      placeholder="Measles genotype A probe"
                      maxLength={maxInputLength}
                      value={textInput}
                      onChange={handleChange}
                      required
                      isTextArea>
                    </CharacterCount>
                  </div>
                  <div className="mt-4">
                    <Button type="submit" disabled={textInput.trim().length === 0}>
                      Submit
                    </Button>
                    <strong className="ml-4 !font-light" role="note">
                      Note: Do not input PII/PHI
                    </strong>
                  </div>
                </FormGroup>
              </Form>
            </div>
            <div className="bg-blue-cool-5 max-w-100 rounded-lg p-8 mt-4">
              <h3>
                Standardized output
              </h3>
              <span className="font-extralight">
                Placeholder
              </span>
              <Button>
                <Icon.ContentCopy/> Copy
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}

export default App;

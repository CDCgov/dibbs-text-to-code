export interface Coding {
  code: string;
  codeSystem: string;
  shortName: string;
  longName: string;
}

export interface Result {
  input: string;
  codings: Coding[];
}

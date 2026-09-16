/** A person as the API names them: name, employee code and roles (backlog-issues B12, D13). */
export type Person = { full_name: string; employee_code: string; roles: string[] };

/** "Arun Kulkarni (EMP004, Chef)". */
export function describePerson(person: Person): string {
  return `${person.full_name} (${[person.employee_code, ...person.roles].join(', ')})`;
}

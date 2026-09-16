// Owner defect sheet row 19 (backlog-issues B12): the profile listed `cash.manage`, `cost.view`.
import { describe, expect, it } from 'vitest';

import { Permission } from '@shared/permissions';

import { PERMISSION_WORDS } from './permissionWords';

describe('what each permission lets a person do', () => {
  it('has a sentence for every permission, and none of them is a code', () => {
    for (const code of Object.values(Permission)) {
      const words = PERMISSION_WORDS[code];
      expect(words.length).toBeGreaterThan(10);
      expect(words).not.toMatch(/\b[a-z]+\.[a-z_.]+\b/);
    }
  });
});

# Contributing to Stash

Thanks for helping improve Stash. The project is an early beta, so small, focused changes are easiest to review.

## Before opening a change

- Check existing issues and discussions for related work.
- Describe the behavior you changed and the platforms it affects.
- Include steps to reproduce a bug and the expected result.
- Do not include storage/, local databases, copied media, secrets, signing files, model weights, machine-specific build output, or user-submitted training examples.
- For Ava training examples, use synthetic or reviewed, anonymized data only.

## Code changes

Keep file operations behind the existing validation and confirmation paths. Changes that move, overwrite, or delete user files should preserve preview and explicit confirmation behavior. Avoid adding network access or background data collection without explaining it in the change.

Run the checks relevant to your change before submitting. The repository includes Python/browser checks and Android build, lint, and unit-test workflows. Include the commands and results in the pull request description.

Contributions are expected to be distributed under the project's GNU GPL version 3 license. Third-party components retain their own licenses.

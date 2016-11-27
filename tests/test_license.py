"""
Shanghai - Multiserver Asyncio IRC Bot
Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>

This file is part of Shanghai.

Shanghai is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Shanghai is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
import ast


class TestLicense:

    def test_pyfiles(self):
        files = []
        for path, dirnames, filenames in os.walk('.'):
            if path == '.':
                for ign_dir in ('.tox', '.cache', 'logs', 'Shanghai.egg-info'):
                    if ign_dir not in dirnames:
                        continue
                    dirnames.remove(ign_dir)
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                fullpath = os.path.join(path, filename)
                files.append(fullpath)

        for path in files:
            with open(path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            assert tree.body, 'Empty source file'
            assert isinstance(tree.body[0], ast.Expr), \
                'Excepected doc string at beginning of file {}.'.format(path)
            assert isinstance(tree.body[0].value, ast.Str),\
                'Excepected doc string at beginning of file {}.'.format(path)

            own_doc = self._clean_license(__doc__)
            file_doc = self._clean_license(tree.body[0].value.s)
            assert own_doc == file_doc, 'License header of file {!r} seems incorrect.'.format(path)

    @staticmethod
    def _clean_license(docstring):
        doclines = [line for line in docstring.splitlines() if line.strip()
                    and not line.lower().startswith('copyright © ')]
        return '\n'.join(doclines)

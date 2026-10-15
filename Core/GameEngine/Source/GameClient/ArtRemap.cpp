/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2026 TheSuperHackers
**
**	This program is free software: you can redistribute it and/or modify
**	it under the terms of the GNU General Public License as published by
**	the Free Software Foundation, either version 3 of the License, or
**	(at your option) any later version.
**
**	This program is distributed in the hope that it will be useful,
**	but WITHOUT ANY WARRANTY; without even the implied warranty of
**	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
**	GNU General Public License for more details.
**
**	You should have received a copy of the GNU General Public License
**	along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

// GeneralsX @feature Claude 16/10/2026 Display-only remap of W3D model and animation names, see ArtRemap.h.

#include "PreRTS.h"	// This must go first in EVERY cpp file in the GameEngine

#include "GameClient/ArtRemap.h"

#include "Common/INI.h"

#include <cctype>
#include <map>
#include <string>

namespace
{
// std::string rather than AsciiString: the tables are static and outlive the game's memory pools.
typedef std::map<std::string, std::string> NameTable;

NameTable& modelTable()
{
	static NameTable table;
	return table;
}

NameTable& animationTable()
{
	static NameTable table;
	return table;
}

std::string lowerName(const char* name)
{
	std::string out(name ? name : "");
	for (std::string::iterator it = out.begin(); it != out.end(); ++it)
		*it = static_cast<char>(tolower(static_cast<unsigned char>(*it)));
	return out;
}

void addEntry(NameTable& table, const char* retailName, const char* displayName)
{
	const std::string display = lowerName(displayName);
	table[lowerName(retailName)] = (display == "none") ? std::string() : display;
}

bool findEntry(const NameTable& table, const AsciiString& retailName, AsciiString& displayName)
{
	if (table.empty() || retailName.isEmpty())
		return false;
	NameTable::const_iterator it = table.find(lowerName(retailName.str()));
	if (it == table.end())
		return false;
	displayName = it->second.c_str();
	return true;
}

void parseModelPair(INI* ini, void* /*instance*/, void* /*store*/, const void* /*userData*/)
{
	const char* retailName = ini->getNextToken();
	const char* displayName = ini->getNextToken();
	ArtRemap::addModel(retailName, displayName);
}

void parseAnimationPair(INI* ini, void* /*instance*/, void* /*store*/, const void* /*userData*/)
{
	const char* retailName = ini->getNextToken();
	const char* displayName = ini->getNextToken();
	ArtRemap::addAnimation(retailName, displayName);
}

const FieldParse s_artRemapFieldParseTable[] =
{
	{ "Model", parseModelPair, nullptr, 0 },
	{ "Animation", parseAnimationPair, nullptr, 0 },
	{ nullptr, nullptr, nullptr, 0 }
};
}

void ArtRemap::reset()
{
	modelTable().clear();
	animationTable().clear();
}

void ArtRemap::addModel(const char* retailName, const char* displayName)
{
	addEntry(modelTable(), retailName, displayName);
}

void ArtRemap::addAnimation(const char* retailName, const char* displayName)
{
	addEntry(animationTable(), retailName, displayName);
}

bool ArtRemap::findModel(const AsciiString& retailName, AsciiString& displayName)
{
	return findEntry(modelTable(), retailName, displayName);
}

bool ArtRemap::findAnimation(const AsciiString& retailName, AsciiString& displayName)
{
	return findEntry(animationTable(), retailName, displayName);
}

bool ArtRemap::isEmpty()
{
	return modelTable().empty() && animationTable().empty();
}

//-------------------------------------------------------------------------------------------------
void INI::parseArtRemapDefinition( INI* ini )
{
	// The fields store into the static tables; initFromINI only needs a non-null instance.
	static int s_instance = 0;
	ini->initFromINI(&s_instance, s_artRemapFieldParseTable);
}

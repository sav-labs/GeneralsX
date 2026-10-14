/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2025 Electronic Arts Inc.
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

// FILE: UILayout.h ///////////////////////////////////////////////////////
// GeneralsX @feature Claude 14/10/2026 Shared transform that maps 2D interface
// coordinates authored at a fixed creation resolution (800x600 .wnd layouts,
// 1024x768 DEFAULT_DISPLAY_* constants, ControlBarScheme ScreenCreationRes)
// to the current display.
//
// Retail scales x and y independently, which stretches the interface on
// displays wider than the authored aspect ratio (16:9, 21:9, 32:9). On such
// displays this transform uses one uniform scale based on the display height
// and centers the authored layout horizontally (pillarbox). At exactly the
// authored aspect ratio, and on taller displays (5:4), the result is
// bit-for-bit identical to the retail per-axis scale with no offset.
//
// The interface is client-only presentation; nothing here feeds game logic.

#pragma once

#include "Lib/BaseType.h"
#include "Common/GameDefines.h"
#include "GameClient/Display.h"

struct UILayoutTransform
{
	Real scaleX;		///< multiplier for authored x coordinates and widths
	Real scaleY;		///< multiplier for authored y coordinates and heights
	Int offsetX;		///< pixels added to absolute screen x after scaling
	Int offsetY;		///< pixels added to absolute screen y after scaling
	Bool pillarboxed;	///< TRUE when the display is wider than the layout (uniform scale, centered)

	/// Absolute authored x position to absolute screen x position
	Int toScreenX( Real authoredX ) const { return (Int)(authoredX * scaleX) + offsetX; }
	/// Absolute authored y position to absolute screen y position
	Int toScreenY( Real authoredY ) const { return (Int)(authoredY * scaleY) + offsetY; }
	/// TRUE when the layout is pillarboxed (uniform scale with a horizontal offset)
	Bool isPillarboxed() const { return pillarboxed; }
};

/// Compute the layout transform for a layout authored at createWidth x createHeight
/// shown on a displayWidth x displayHeight display.
inline UILayoutTransform UILayoutComputeTransform( Int displayWidth, Int displayHeight,
																									 Int createWidth, Int createHeight )
{
	UILayoutTransform t;
	t.offsetX = 0;
	t.offsetY = 0;
	t.pillarboxed = FALSE;

	if( createWidth <= 0 || createHeight <= 0 || displayWidth <= 0 || displayHeight <= 0 )
	{
		t.scaleX = 1.0f;
		t.scaleY = 1.0f;
		return t;
	}

	// Retail per-axis scale. Kept as is for the authored aspect ratio and taller displays,
	// where a vertical gap above the control bar would be worse than a slight stretch.
	t.scaleX = (Real)displayWidth / (Real)createWidth;
	t.scaleY = (Real)displayHeight / (Real)createHeight;

	// Wider than the authored aspect ratio: exact integer comparison so that every
	// true 4:3 mode (800x600, 1024x768, 1600x1200, ...) keeps the retail path.
	// Products stay far below INT_MAX for any real display and creation resolution.
	if( displayWidth * createHeight > displayHeight * createWidth )
	{
		t.pillarboxed = TRUE;
		t.scaleX = t.scaleY;
		const Int layoutWidth = (Int)((Real)createWidth * t.scaleY);
		t.offsetX = (displayWidth - layoutWidth) / 2;
	}

	return t;
}

/// Layout transform for the current display
inline UILayoutTransform UILayoutGetTransform( Int createWidth, Int createHeight )
{
	if( TheDisplay == nullptr )
		return UILayoutComputeTransform( createWidth, createHeight, createWidth, createHeight );

	return UILayoutComputeTransform( (Int)TheDisplay->getWidth(), (Int)TheDisplay->getHeight(),
																	 createWidth, createHeight );
}

/// Layout transform for coordinates expressed against DEFAULT_DISPLAY_WIDTH x DEFAULT_DISPLAY_HEIGHT
inline UILayoutTransform UILayoutGetDefaultTransform()
{
	return UILayoutGetTransform( DEFAULT_DISPLAY_WIDTH, DEFAULT_DISPLAY_HEIGHT );
}

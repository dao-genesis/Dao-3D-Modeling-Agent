# SolidWorks COM 本源 · Python 早绑定索引

> 反者道之动 · 大曰逝,逝曰远,远曰反 · 目无全牛 · 一劳永逸

生成于 2026-04-23 10:49:26  ·  耗时 0.1s

**汇总**: 498 类 · 9264 方法 · 11607 枚举常量

## 本源模块

| 模块 | 文件 | 大小 | 行数 | 类 | 方法 | 枚举 |
|---|---|---:|---:|---:|---:|---:|
| `swconst` | `swconst.py` | 649KB | 7989 | 0 | 0 | 7944 |
| `sldworks` | `sldworks.py` | 6056KB | 100797 | 484 | 9189 | 0 |
| `swcommands` | `swcommands.py` | 252KB | 3682 | 0 | 0 | 3637 |
| `swpublished` | `swpublished.py` | 68KB | 1028 | 0 | 0 | 0 |
| `swmotionstudy` | `swmotionstudy.py` | 51KB | 1007 | 10 | 59 | 26 |
| `swvba` | `swvba.py` | 12KB | 311 | 4 | 16 | 0 |

## 核心接口速查 (sldworks 前 30 最大接口)

| 接口 | 方法数 |
|---|---:|
| `IModelDoc2` | 758 |
| `IModelDoc` | 684 |
| `IView` | 422 |
| `ISldWorks` | 327 |
| `IModelDocExtension` | 320 |
| `IDrawingDoc` | 270 |
| `IFeatureManager` | 264 |
| `IBody2` | 210 |
| `IAssemblyDoc` | 196 |
| `IPartDoc` | 166 |
| `IComponent2` | 140 |
| `IModeler` | 125 |
| `IGtol` | 118 |
| `IBody` | 117 |
| `IFeature` | 115 |
| `IFace2` | 112 |
| `INote` | 112 |
| `IDisplayDimension` | 102 |
| `ISketch` | 102 |
| `IAnnotation` | 83 |
| `ISketchManager` | 83 |
| `IFace` | 74 |
| `ITableAnnotation` | 73 |
| `ISurface` | 72 |
| `ICurve` | 65 |
| `IMacroFeatureData` | 65 |
| `IConfiguration` | 62 |
| `IDisplayData` | 59 |
| `ISelectionMgr` | 59 |
| `IComponent` | 53 |

## swconst 枚举族 (共 946 族)

| 枚举族 | 成员数 | 样例成员 |
|---|---:|---|
| `swUserPreferenceToggle_e` | 762 | `sw3DPDFCompressLossyTessellation`, `sw3MFAppearances`, `sw3MFDecals` |
| `swUserPreferenceIntegerValue_e` | 607 | `sw3DPDFAccuracy`, `swAcisOutputGeometryPreference`, `swAcisOutputUnits` |
| `swWzdHoleStandardFastenerTypes_e` | 404 | `swStandardASBottomingTappedHole`, `swStandardASCheeseHeadScrew`, `swStandardASCrossCountersunkHeadScrew` |
| `swUserPreferenceDoubleValue_e` | 216 | `swASMSLDPRT_ExcludeComponentsByBBoxVolumeThreshold`, `swASMSLDPRT_ExcludeComponentsByVisibilityThreshold`, `swAnnotationTextScaleDenominator` |
| `swSelectType_e` | 147 | `SwSelMAGNETICLINES`, `swSelADVSTRUCTMEMBER`, `swSelANNOTATIONTABLES` |
| `swUserPreferenceStringValue_e` | 134 | `swAutoSaveDirectory`, `swBackupDirectory`, `swBomTableBOMHeaderCustomText_ForIndentedBOM` |
| `swFeatureNameID_e` | 128 | `swFmAEM3DContact`, `swFmAEMGravity`, `swFmAEMLinearDamper` |
| `swAssemblyNotify_e` | 97 | `swAssemblyActiveDisplayStateChangePostNotify`, `swAssemblyActiveDisplayStateChangePreNotify`, `swAssemblyActiveViewChangeNotify` |
| `swCalloutVariable_e` | 90 | `swCalloutVariable_AH_Blind_Msg`, `swCalloutVariable_AH_Counterbore_Depth`, `swCalloutVariable_AH_Counterbore_Diameter` |
| `swConstraintType_e` | 86 | `swConstraintType_ALONGX`, `swConstraintType_ALONGX3D`, `swConstraintType_ALONGXPOINTS` |
| `swWzdHoleTypes_e` | 81 | `swCounterBoreBlind`, `swCounterBoreBlindCounterSinkMiddle`, `swCounterBoreBlindCounterSinkTop` |
| `swPartNotify_e` | 79 | `swPartActiveDisplayStateChangePostNotify`, `swPartActiveDisplayStateChangePreNotify`, `swPartActiveViewChangeNotify` |
| `swDrawingNotify_e` | 57 | `swDrawingActivateSheetPostNotify`, `swDrawingActivateSheetPreNotify`, `swDrawingAddCustomPropertyNotify` |
| `swFeatureError_e` | 53 | `swFeatureErrorExtrusionBadGeometricConditions`, `swFeatureErrorExtrusionBossContourInvalid`, `swFeatureErrorExtrusionBossContourOpenAndClosed` |
| `swUserPreferenceTextFormat_e` | 50 | `swDetailingAnnotationTextFormat`, `swDetailingAuxView_DelimiterTextFormat`, `swDetailingAuxView_LabelTextFormat` |
| `swToolbar_e` | 45 | `sw2Dto3DToolbar`, `swAlignToolbar`, `swAnimationPaneToolbar` |
| `swDimensionSymbol_e` | 41 | `swDimensionSymbol_Angle`, `swDimensionSymbol_CalloutText`, `swDimensionSymbol_CenterOfMass` |
| `swAppNotify_e` | 38 | `swAppActiveDocChangeNotify`, `swAppActiveModelDocChangeNotify`, `swAppBackgroundProcessingEndNotify` |
| `swPropertyManagerPageBitmapButtons_e` | 38 | `swBitmapButtonImage_alongz`, `swBitmapButtonImage_angle`, `swBitmapButtonImage_auto_bal_circular` |
| `swTableColumnTypes_e` | 38 | `swBendTableColumnType_Angle`, `swBendTableColumnType_BendAllowance`, `swBendTableColumnType_BendOrder` |
| `swQuickTipPointAt_e` | 37 | `swQTPA_ArrowManipulator`, `swQTPA_AssemblyComponentFeature`, `swQTPA_AssemblyComponentNonFixed` |
| `swFaultEntityErrorCode_e` | 36 | `swBodyCorrupt`, `swBodyInsideOut`, `swBodyInvalidIdentifiers` |
| `swDesignTableErrors_e` | 34 | `swDTConfigCircularDefinition`, `swDTDimAngleValueRangeError`, `swDTDimValueRangeError` |
| `swKernelErrorCode_e` | 34 | `swErrorBodyDontKnit`, `swErrorCheckFailed`, `swErrorCheckFailed2` |
| `swMotionPlotAxisType_e` | 34 | `swMotionPlotAxisType_ANGULAR_ACCEL`, `swMotionPlotAxisType_ANGULAR_DISP`, `swMotionPlotAxisType_ANGULAR_KINETIC_ENERGY` |
| `swUserPreferenceOption_e` | 34 | `swDetailingAngleDimension`, `swDetailingAngularRunningDimension`, `swDetailingAnnotation` |
| `swParasolidOutputVersion_e` | 33 | `swParasolidOutputVersion_100`, `swParasolidOutputVersion_110`, `swParasolidOutputVersion_111` |
| `swPresentationOpts_e` | 32 | `swPresentationOpts_ActiveView`, `swPresentationOpts_Animations`, `swPresentationOpts_BackView` |
| `swRunMacroError_e` | 28 | `swRunMacroError_BadParmCount`, `swRunMacroError_BadVarType`, `swRunMacroError_Busy` |
| `swPrompForFilenameCause_e` | 27 | `swAddComponent`, `swAddVirtualComponent`, `swComponentPropsReplace` |
| `swMateType_e` | 26 | `swMateANGLE`, `swMateCAMFOLLOWER`, `swMateCOINCIDENT` |
| `swControlBitmapLabelType_e` | 25 | `swBitmapLabel_AngularDistance`, `swBitmapLabel_BendAllowance`, `swBitmapLabel_BendDeduction` |
| `swFileLoadError_e` | 25 | `swAddinInteruptError`, `swApplicationBusy`, `swBasePartNotLoadedWarn` |
| `swInsertAnnotation_e` | 25 | `swInsertAxes`, `swInsertCThreads`, `swInsertCurves` |
| `swSketchCheckFeatureStatus_e` | 25 | `swSketchCheckFeatureStatus_ClosedWantOpen`, `swSketchCheckFeatureStatus_ContourIntersectsCenterLine`, `swSketchCheckFeatureStatus_CturXCtur` |
| `swAcisOutputVersion_e` | 24 | `swAcisOutputVersion_100`, `swAcisOutputVersion_110`, `swAcisOutputVersion_120` |
| `swInsertPartOptions_e` | 24 | `swInsertPartBreakLink`, `swInsertPartDontZoomAll`, `swInsertPartImportAbsorbedSketchs` |
| `swQuickTipMode_e` | 24 | `swQuickTipAssemblyMatedMode`, `swQuickTipAssemblyMultiCompMode`, `swQuickTipAssemblyOneCompMode` |
| `swSketchCheckFeatureProfileUsage_e` | 24 | `swSketchCheckFeature_BASEEXTRUDE`, `swSketchCheckFeature_BASEEXTRUDETHIN`, `swSketchCheckFeature_BASEREVOLVE` |
| `swBalloonStyle_e` | 21 | `swBS_ArcBracket`, `swBS_ArclenSym`, `swBS_Box` |

## 常用入口 (速查清单)

- **连接 SW**: `win32com.client.GetActiveObject('SldWorks.Application')`
- **装配体**: `IAssemblyDoc` · `GetComponents(True)` 取全组件
- **组件定位**: `IComponent2.Transform2` (Get/Set MathTransform)
- **零件替换**: `IAssemblyDoc.ReplaceComponents` (config/newname/opts)
- **导入 STEP**: `ISldWorks.LoadFile4(path, arg)` → `IPartDoc`
- **另存 SLDPRT**: `IModelDoc2.SaveAs3(path, version, opts)`
- **重建**: `IModelDoc2.EditRebuild3` / `ForceRebuild3(TopOnly)`
- **保存装配**: `IModelDoc2.Save3(opts, errors, warnings)`
- **bbox**: `IPartDoc.GetPartBox(useRefGeom, includeHidden, noRefs)`
- **组件 bbox**: `IComponent2.GetBox(noRefs, noChild)` (低版兼容 `GetBox(False, False)` 双参)
- **刚体固定**: `IComponent2.SetSuppression2(swComponentResolved)` + `Select4+FixComponent`

## 关键枚举常量 (高频)

| 名 | 值 | 含义 |
|---|---:|---|
| `swDocPART` | 1 | 零件 |
| `swDocASSEMBLY` | 2 | 装配体 |
| `swDocDRAWING` | 3 | 工程图 |
| `swSaveAsCurrentVersion` | 0 | SaveAs 版本 |
| `swSaveAsOptions_Silent` | 1 | 静默保存 |
| `swRebuildAll` | 1 | 全部重建 |
| `swComponentSuppressed` | 0 | 组件抑制 |
| `swComponentFullyResolved` | 2 | 组件完全解析 |
| `swImportedType_STEPAP214` | 5 | STEP AP214 |

> 更多枚举见 `sw_api/INDEX.json` (`modules.swconst.enum_families`).
/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2020 - 2025 Intel Corporation
 */

#ifndef IPU7_BUTTRESS_REGS_H
#define IPU7_BUTTRESS_REGS_H

#define BUTTRESS_REG_IRQ_STATUS					0x2000
#define BUTTRESS_REG_IRQ_STATUS_UNMASKED			0x2004
#define BUTTRESS_REG_IRQ_ENABLE					0x2008
#define BUTTRESS_REG_IRQ_CLEAR					0x200c
#define BUTTRESS_REG_IRQ_MASK					0x2010
#define BUTTRESS_REG_TSC_CMD					0x2014
#define BUTTRESS_REG_TSC_CTL					0x2018
#define BUTTRESS_REG_TSC_LO					0x201c
#define BUTTRESS_REG_TSC_HI					0x2020

/* valid for PTL */
#define BUTTRESS_REG_PB_TIMESTAMP_LO				0x2030
#define BUTTRESS_REG_PB_TIMESTAMP_HI				0x2034
#define BUTTRESS_REG_PB_TIMESTAMP_VALID				0x2038

#define BUTTRESS_REG_PS_WORKPOINT_REQ				0x2100
#define BUTTRESS_REG_IS_WORKPOINT_REQ				0x2104
#define BUTTRESS_REG_PS_WORKPOINT_DOMAIN_REQ			0x2108
#define BUTTRESS_REG_PS_DOMAINS_STATUS				0x2110
#define BUTTRESS_REG_PWR_STATUS					0x2114
#define BUTTRESS_REG_PS_WORKPOINT_REQ_SHADOW			0x2120
#define BUTTRESS_REG_IS_WORKPOINT_REQ_SHADOW			0x2124
#define BUTTRESS_REG_PS_WORKPOINT_DOMAIN_REQ_SHADOW		0x2128
#define BUTTRESS_REG_ISPS_WORKPOINT_DOWNLOAD			0x212c
#define BUTTRESS_REG_PG_FLOW_OVERRIDE				0x2180
#define BUTTRESS_REG_GLOBAL_OVERRIDE_UNGATE_CTL			0x2184
#define BUTTRESS_REG_PWR_FSM_CTL				0x2188
#define BUTTRESS_REG_IDLE_WDT					0x218c
#define BUTTRESS_REG_PS_PWR_DOMAIN_EVENTQ_EN			0x2190
#define BUTTRESS_REG_PS_PWR_DOMAIN_EVENTQ_ADDR			0x2194
#define BUTTRESS_REG_PS_PWR_DOMAIN_EVENTQ_DATA			0x2198
#define BUTTRESS_REG_POWER_EN_DELAY				0x219c
#define IPU7_BUTTRESS_REG_LTR_CONTROL				0x21a0
#define IPU7_BUTTRESS_REG_NDE_CONTROL				0x21a4
#define IPU7_BUTTRESS_REG_INT_FRM_PUNIT				0x21a8
#define IPU8_BUTTRESS_REG_LTR_CONTROL				0x21a4
#define IPU8_BUTTRESS_REG_NDE_CONTROL				0x21a8
#define IPU8_BUTTRESS_REG_INT_FRM_PUNIT				0x21ac
#define BUTTRESS_REG_SLEEP_LEVEL_CFG				0x21b0
#define BUTTRESS_REG_SLEEP_LEVEL_STS				0x21b4
#define BUTTRESS_REG_DVFS_FSM_STATUS				0x21b8
#define BUTTRESS_REG_PS_PLL_ENABLE				0x21bc
#define BUTTRESS_REG_D2D_CTL					0x21d4
#define BUTTRESS_REG_IB_CLK_CTL					0x21d8
#define BUTTRESS_REG_IB_CRO_CLK_CTL				0x21dc
#define BUTTRESS_REG_FUNC_FUSES					0x21e0
#define BUTTRESS_REG_ISOCH_CTL					0x21e4
#define BUTTRESS_REG_WORKPOINT_CTL				0x21f0
#define BUTTRESS_REG_DRV_IS_UCX_CONTROL_STATUS			0x2200
#define BUTTRESS_REG_DRV_IS_UCX_START_ADDR			0x2204
#define BUTTRESS_REG_DRV_PS_UCX_CONTROL_STATUS			0x2208
#define BUTTRESS_REG_DRV_PS_UCX_START_ADDR			0x220c
#define BUTTRESS_REG_DRV_UCX_RESET_CFG				0x2210

/* configured by CSE */
#define BUTTRESS_REG_CSE_IS_UCX_CONTROL_STATUS			0x2300
#define BUTTRESS_REG_CSE_IS_UCX_START_ADDR			0x2304
#define BUTTRESS_REG_CSE_PS_UCX_CONTROL_STATUS			0x2308
#define BUTTRESS_REG_CSE_PS_UCX_START_ADDR			0x230c

#define BUTTRESS_REG_CAMERA_MASK				0x2310
#define BUTTRESS_REG_FW_CTL					0x2314
#define BUTTRESS_REG_SECURITY_CTL				0x2318
#define BUTTRESS_REG_FUNCTIONAL_FW_SETUP			0x231c
#define BUTTRESS_REG_FW_BASE					0x2320
#define BUTTRESS_REG_FW_BASE_LIMIT				0x2324
#define BUTTRESS_REG_FW_SCRATCH_BASE				0x2328
#define BUTTRESS_REG_FW_SCRATCH_LIMIT				0x232c
#define BUTTRESS_REG_CSE_ACTION					0x2330

/* configured by SW */
#define BUTTRESS_REG_FW_RESET_CTL				0x2334
#define BUTTRESS_REG_FW_SOURCE_SIZE				0x2338
#define BUTTRESS_REG_FW_SOURCE_BASE				0x233c

#define BUTTRESS_REG_IPU_SEC_CP_LSB				0x2400
#define BUTTRESS_REG_IPU_SEC_CP_MSB				0x2404
#define BUTTRESS_REG_IPU_SEC_WAC_LSB				0x2408
#define BUTTRESS_REG_IPU_SEC_WAC_MSB				0x240c
#define BUTTRESS_REG_IPU_SEC_RAC_LSB				0x2410
#define BUTTRESS_REG_IPU_SEC_RAC_MSB				0x2414
#define BUTTRESS_REG_IPU_DRV_CP_LSB				0x2418
#define BUTTRESS_REG_IPU_DRV_CP_MSB				0x241c
#define BUTTRESS_REG_IPU_DRV_WAC_LSB				0x2420
#define BUTTRESS_REG_IPU_DRV_WAC_MSB				0x2424
#define BUTTRESS_REG_IPU_DRV_RAC_LSB				0x2428
#define BUTTRESS_REG_IPU_DRV_RAC_MSB				0x242c
#define BUTTRESS_REG_IPU_FW_CP_LSB				0x2430
#define BUTTRESS_REG_IPU_FW_CP_MSB				0x2434
#define BUTTRESS_REG_IPU_FW_WAC_LSB				0x2438
#define BUTTRESS_REG_IPU_FW_WAC_MSB				0x243c
#define BUTTRESS_REG_IPU_FW_RAC_LSB				0x2440
#define BUTTRESS_REG_IPU_FW_RAC_MSB				0x2444
#define BUTTRESS_REG_IPU_BIOS_SEC_CP_LSB			0x2448
#define BUTTRESS_REG_IPU_BIOS_SEC_CP_MSB			0x244c
#define BUTTRESS_REG_IPU_BIOS_SEC_WAC_LSB			0x2450
#define BUTTRESS_REG_IPU_BIOS_SEC_WAC_MSB			0x2454
#define BUTTRESS_REG_IPU_BIOS_SEC_RAC_LSB			0x2458
#define BUTTRESS_REG_IPU_BIOS_SEC_RAC_MSB			0x245c
#define BUTTRESS_REG_IPU_DFD_CP_LSB				0x2460
#define BUTTRESS_REG_IPU_DFD_CP_MSB				0x2464
#define BUTTRESS_REG_IPU_DFD_WAC_LSB				0x2468
#define BUTTRESS_REG_IPU_DFD_WAC_MSB				0x246c
#define BUTTRESS_REG_IPU_DFD_RAC_LSB				0x2470
#define BUTTRESS_REG_IPU_DFD_RAC_MSB				0x2474
#define BUTTRESS_REG_CSE2IUDB0					0x2500
#define BUTTRESS_REG_CSE2IUDATA0				0x2504
#define BUTTRESS_REG_CSE2IUCSR					0x2508
#define BUTTRESS_REG_IU2CSEDB0					0x250c
#define BUTTRESS_REG_IU2CSEDATA0				0x2510
#define BUTTRESS_REG_IU2CSECSR					0x2514
#define BUTTRESS_REG_CSE2IUDB0_CR_SHADOW			0x2520
#define BUTTRESS_REG_CSE2IUDATA0_CR_SHADOW			0x2524
#define BUTTRESS_REG_CSE2IUCSR_CR_SHADOW			0x2528
#define BUTTRESS_REG_IU2CSEDB0_CR_SHADOW			0x252c
#define BUTTRESS_REG_DVFS_FSM_SURVIVABILITY			0x2900
#define BUTTRESS_REG_FLOWS_FSM_SURVIVABILITY			0x2904
#define BUTTRESS_REG_FABRICS_FSM_SURVIVABILITY			0x2908
#define BUTTRESS_REG_PS_SUB1_PM_FSM_SURVIVABILITY		0x290c
#define BUTTRESS_REG_PS_SUB0_PM_FSM_SURVIVABILITY		0x2910
#define BUTTRESS_REG_PS_PM_FSM_SURVIVABILITY			0x2914
#define BUTTRESS_REG_IS_PM_FSM_SURVIVABILITY			0x2918
#define BUTTRESS_REG_FLR_RST_FSM_SURVIVABILITY			0x291c
#define BUTTRESS_REG_FW_RST_FSM_SURVIVABILITY			0x2920
#define BUTTRESS_REG_RESETPREP_FSM_SURVIVABILITY		0x2924
#define BUTTRESS_REG_POWER_FSM_DOMAIN_STATUS			0x3000
#define BUTTRESS_REG_IDLEREQ_STATUS1				0x3004
#define BUTTRESS_REG_POWER_FSM_STATUS_IS_PS			0x3008
#define BUTTRESS_REG_POWER_ACK_B_STATUS				0x300c
#define BUTTRESS_REG_DOMAIN_RETENTION_CTL			0x3010
#define BUTTRESS_REG_CG_CTRL_BITS				0x3014
#define BUTTRESS_REG_IS_IFC_STATUS0				0x3018
#define BUTTRESS_REG_IS_IFC_STATUS1				0x301c
#define BUTTRESS_REG_PS_IFC_STATUS0				0x3020
#define BUTTRESS_REG_PS_IFC_STATUS1				0x3024
#define BUTTRESS_REG_BTRS_IFC_STATUS0				0x3028
#define BUTTRESS_REG_BTRS_IFC_STATUS1				0x302c
#define BUTTRESS_REG_IPU_SKU					0x3030
#define BUTTRESS_REG_PS_IDLEACK					0x3034
#define BUTTRESS_REG_IS_IDLEACK					0x3038
#define BUTTRESS_REG_SPARE_REGS_0				0x303c
#define BUTTRESS_REG_SPARE_REGS_1				0x3040
#define BUTTRESS_REG_SPARE_REGS_2				0x3044
#define BUTTRESS_REG_SPARE_REGS_3				0x3048
#define BUTTRESS_REG_IUNIT_ACV					0x304c
#define BUTTRESS_REG_CHICKEN_BITS				0x3050
#define BUTTRESS_REG_SBENDPOINT_CFG				0x3054
#define BUTTRESS_REG_ECC_ERR_LOG				0x3058
#define BUTTRESS_REG_POWER_FSM_STATUS				0x3070
#define BUTTRESS_REG_RESET_FSM_STATUS				0x3074
#define BUTTRESS_REG_IDLE_STATUS				0x3078
#define BUTTRESS_REG_IDLEACK_STATUS				0x307c
#define BUTTRESS_REG_IPU_DEBUG					0x3080

#define BUTTRESS_REG_FW_BOOT_PARAMS0				0x4000
#define BUTTRESS_REG_FW_BOOT_PARAMS1				0x4004
#define BUTTRESS_REG_FW_BOOT_PARAMS2				0x4008
#define BUTTRESS_REG_FW_BOOT_PARAMS3				0x400c
#define BUTTRESS_REG_FW_BOOT_PARAMS4				0x4010
#define BUTTRESS_REG_FW_BOOT_PARAMS5				0x4014
#define BUTTRESS_REG_FW_BOOT_PARAMS6				0x4018
#define BUTTRESS_REG_FW_BOOT_PARAMS7				0x401c
#define BUTTRESS_REG_FW_BOOT_PARAMS8				0x4020
#define BUTTRESS_REG_FW_BOOT_PARAMS9				0x4024
#define BUTTRESS_REG_FW_BOOT_PARAMS10				0x4028
#define BUTTRESS_REG_FW_BOOT_PARAMS11				0x402c
#define BUTTRESS_REG_FW_BOOT_PARAMS12				0x4030
#define BUTTRESS_REG_FW_BOOT_PARAMS13				0x4034
#define BUTTRESS_REG_FW_BOOT_PARAMS14				0x4038
#define BUTTRESS_REG_FW_BOOT_PARAMS15				0x403c

#define BUTTRESS_FW_BOOT_PARAMS_ENTRY(i) \
	(BUTTRESS_REG_FW_BOOT_PARAMS0 + ((i) * 4U))
#define BUTTRESS_REG_FW_GP(i)				(0x4040 + 0x4 * (i))
#define BUTTRESS_REG_FPGA_SUPPORT(i)			(0x40c0 + 0x4 * (i))

#define BUTTRESS_REG_FW_GP8					0x4060
#define BUTTRESS_REG_FW_GP24					0x40a0

#define BUTTRESS_REG_GPIO_0_PADCFG_ADDR_CR			0x4100
#define BUTTRESS_REG_GPIO_1_PADCFG_ADDR_CR			0x4104
#define BUTTRESS_REG_GPIO_2_PADCFG_ADDR_CR			0x4108
#define BUTTRESS_REG_GPIO_3_PADCFG_ADDR_CR			0x410c
#define BUTTRESS_REG_GPIO_4_PADCFG_ADDR_CR			0x4110
#define BUTTRESS_REG_GPIO_5_PADCFG_ADDR_CR			0x4114
#define BUTTRESS_REG_GPIO_6_PADCFG_ADDR_CR			0x4118
#define BUTTRESS_REG_GPIO_7_PADCFG_ADDR_CR			0x411c
#define BUTTRESS_REG_GPIO_ENABLE				0x4140
#define BUTTRESS_REG_GPIO_VALUE_CR				0x4144

#define BUTTRESS_REG_IS_MEM_CORRECTABLE_ERROR_STATUS		0x5000
#define BUTTRESS_REG_IS_MEM_FATAL_ERROR_STATUS			0x5004
#define BUTTRESS_REG_IS_MEM_NON_FATAL_ERROR_STATUS		0x5008
#define BUTTRESS_REG_IS_MEM_CHECK_PASSED			0x500c
#define BUTTRESS_REG_IS_MEM_ERROR_INJECT			0x5010
#define BUTTRESS_REG_IS_MEM_ERROR_CLEAR				0x5014
#define BUTTRESS_REG_PS_MEM_CORRECTABLE_ERROR_STATUS		0x5040
#define BUTTRESS_REG_PS_MEM_FATAL_ERROR_STATUS			0x5044
#define BUTTRESS_REG_PS_MEM_NON_FATAL_ERROR_STATUS		0x5048
#define BUTTRESS_REG_PS_MEM_CHECK_PASSED			0x504c
#define BUTTRESS_REG_PS_MEM_ERROR_INJECT			0x5050
#define BUTTRESS_REG_PS_MEM_ERROR_CLEAR				0x5054

#define BUTTRESS_REG_IS_AB_REGION_MIN_ADDRESS(i)	(0x6000 + 0x8 * (i))
#define BUTTRESS_REG_IS_AB_REGION_MAX_ADDRESS(i)	(0x6004 + 0x8 * (i))
#define BUTTRESS_REG_IS_AB_VIOLATION_LOG0			0x6080
#define BUTTRESS_REG_IS_AB_VIOLATION_LOG1			0x6084
#define BUTTRESS_REG_PS_AB_REGION_MIN_ADDRESS(i)	(0x6100 + 0x8 * (i))
#define BUTTRESS_REG_PS_AB_REGION_MAX_ADDRESS0		(0x6104 + 0x8 * (i))
#define BUTTRESS_REG_PS_AB_VIOLATION_LOG0			0x6180
#define BUTTRESS_REG_PS_AB_VIOLATION_LOG1			0x6184
#define BUTTRESS_REG_PS_DEBUG_AB_VIOLATION_LOG0			0x6200
#define BUTTRESS_REG_PS_DEBUG_AB_VIOLATION_LOG1			0x6204
#define BUTTRESS_REG_IS_DEBUG_AB_VIOLATION_LOG0			0x6208
#define BUTTRESS_REG_IS_DEBUG_AB_VIOLATION_LOG1			0x620c
#define BUTTRESS_REG_IB_DVP_AB_VIOLATION_LOG0			0x6210
#define BUTTRESS_REG_IB_DVP_AB_VIOLATION_LOG1			0x6214
#define BUTTRESS_REG_IB_ATB2DTF_AB_VIOLATION_LOG0		0x6218
#define BUTTRESS_REG_IB_ATB2DTF_AB_VIOLATION_LOG1		0x621c
#define BUTTRESS_REG_AB_ENABLE					0x6220
#define BUTTRESS_REG_AB_DEFAULT_ACCESS				0x6230

/* Indicates CSE has received an IPU driver IPC transaction */
#define BUTTRESS_IRQ_IPC_EXEC_DONE_BY_CSE		BIT(0)
/* Indicates an IPC transaction from CSE has arrived */
#define BUTTRESS_IRQ_IPC_FROM_CSE_IS_WAITING		BIT(1)
/* Indicates a CSR update from CSE has arrived */
#define BUTTRESS_IRQ_CSE_CSR_SET			BIT(2)
/* Indicates an interrupt set by Punit (not in use at this time) */
#define BUTTRESS_IRQ_PUNIT_2_IUNIT_IRQ			BIT(3)
/* Indicates an SAI violation was detected on access to IB registers */
#define BUTTRESS_IRQ_SAI_VIOLATION			BIT(4)
/* Indicates a transaction to IS was not able to pass the access blocker */
#define BUTTRESS_IRQ_IS_AB_VIOLATION			BIT(5)
/* Indicates a transaction to PS was not able to pass the access blocker */
#define BUTTRESS_IRQ_PS_AB_VIOLATION			BIT(6)
/* Indicates an error response was detected by the IB config NoC */
#define BUTTRESS_IRQ_IB_CFG_NOC_ERR_IRQ			BIT(7)
/* Indicates an error response was detected by the IB data NoC */
#define BUTTRESS_IRQ_IB_DATA_NOC_ERR_IRQ		BIT(8)
/* Transaction to DVP regs was not able to pass the access blocker */
#define BUTTRESS_IRQ_IB_DVP_AB_VIOLATION		BIT(9)
/* Transaction to ATB2DTF regs was not able to pass the access blocker */
#define BUTTRESS_IRQ_ATB2DTF_AB_VIOLATION		BIT(10)
/* Transaction to IS debug regs was not able to pass the access blocker */
#define BUTTRESS_IRQ_IS_DEBUG_AB_VIOLATION		BIT(11)
/* Transaction to PS debug regs was not able to pass the access blocker */
#define BUTTRESS_IRQ_PS_DEBUG_AB_VIOLATION		BIT(12)
/* Indicates timeout occurred waiting for a response from a target */
#define BUTTRESS_IRQ_IB_CFG_NOC_TIMEOUT_IRQ		BIT(13)
/* Set when any correctable ECC error input wire to buttress is set */
#define BUTTRESS_IRQ_ECC_CORRECTABLE			BIT(14)
/* Any noncorrectable-nonfatal ECC error input wire to buttress is set */
#define BUTTRESS_IRQ_ECC_NONCORRECTABLE_NONFATAL	BIT(15)
/* Set when any noncorrectable-fatal ECC error input wire to buttress is set */
#define BUTTRESS_IRQ_ECC_NONCORRECTABLE_FATAL		BIT(16)
/* Set when timeout occurred waiting for a response from a target */
#define BUTTRESS_IRQ_IS_CFG_NOC_TIMEOUT_IRQ		BIT(17)
#define BUTTRESS_IRQ_PS_CFG_NOC_TIMEOUT_IRQ		BIT(18)
#define BUTTRESS_IRQ_LB_CFG_NOC_TIMEOUT_IRQ		BIT(19)
/* IS FW double exception event */
#define BUTTRESS_IRQ_IS_UC_PFATAL_ERROR			BIT(26)
/* PS FW double exception event */
#define BUTTRESS_IRQ_PS_UC_PFATAL_ERROR			BIT(27)
/* IS FW watchdog event */
#define BUTTRESS_IRQ_IS_WATCHDOG			BIT(28)
/* PS FW watchdog event */
#define BUTTRESS_IRQ_PS_WATCHDOG			BIT(29)
/* IS IRC irq out */
#define BUTTRESS_IRQ_IS_IRQ				BIT(30)
/* PS IRC irq out */
#define BUTTRESS_IRQ_PS_IRQ				BIT(31)

/* buttress irq */
#define	BUTTRESS_PWR_STATUS_HH_STATE_IDLE	0U
#define	BUTTRESS_PWR_STATUS_HH_STATE_IN_PRGS	1U
#define	BUTTRESS_PWR_STATUS_HH_STATE_DONE	2U
#define	BUTTRESS_PWR_STATUS_HH_STATE_ERR	3U

#define BUTTRESS_TSC_CMD_START_TSC_SYNC		BIT(0)
#define BUTTRESS_PWR_STATUS_HH_STATUS_SHIFT	11
#define BUTTRESS_PWR_STATUS_HH_STATUS_MASK	(0x3U << 11)
#define BUTTRESS_TSW_WA_SOFT_RESET		BIT(8)
/* new for PTL */
#define BUTTRESS_SEL_PB_TIMESTAMP		BIT(9)
#define BUTTRESS_IRQS		(BUTTRESS_IRQ_IS_IRQ | \
				 BUTTRESS_IRQ_PS_IRQ | \
				 BUTTRESS_IRQ_IPC_FROM_CSE_IS_WAITING | \
				 BUTTRESS_IRQ_CSE_CSR_SET | \
				 BUTTRESS_IRQ_IPC_EXEC_DONE_BY_CSE | \
				 BUTTRESS_IRQ_PUNIT_2_IUNIT_IRQ)

/* Iunit to CSE regs */
#define BUTTRESS_IU2CSEDB0_BUSY		BIT(31)
#define BUTTRESS_IU2CSEDB0_SHORT_FORMAT_SHIFT	27
#define BUTTRESS_IU2CSEDB0_CLIENT_ID_SHIFT	10
#define BUTTRESS_IU2CSEDB0_IPC_CLIENT_ID_VAL	2

#define BUTTRESS_IU2CSEDATA0_IPC_BOOT_LOAD		1
#define BUTTRESS_IU2CSEDATA0_IPC_AUTH_RUN		2
#define BUTTRESS_IU2CSEDATA0_IPC_AUTH_REPLACE		3
#define BUTTRESS_IU2CSEDATA0_IPC_UPDATE_SECURE_TOUCH	16

#define BUTTRESS_CSE2IUDATA0_IPC_BOOT_LOAD_DONE			BIT(0)
#define BUTTRESS_CSE2IUDATA0_IPC_AUTH_RUN_DONE			BIT(1)
#define BUTTRESS_CSE2IUDATA0_IPC_AUTH_REPLACE_DONE		BIT(2)
#define BUTTRESS_CSE2IUDATA0_IPC_UPDATE_SECURE_TOUCH_DONE	BIT(4)

#define BUTTRESS_IU2CSECSR_IPC_PEER_COMP_ACTIONS_RST_PHASE1		BIT(0)
#define BUTTRESS_IU2CSECSR_IPC_PEER_COMP_ACTIONS_RST_PHASE2		BIT(1)
#define BUTTRESS_IU2CSECSR_IPC_PEER_QUERIED_IP_COMP_ACTIONS_RST_PHASE	BIT(2)
#define BUTTRESS_IU2CSECSR_IPC_PEER_ASSERTED_REG_VALID_REQ		BIT(3)
#define BUTTRESS_IU2CSECSR_IPC_PEER_ACKED_REG_VALID			BIT(4)
#define BUTTRESS_IU2CSECSR_IPC_PEER_DEASSERTED_REG_VALID_REQ		BIT(5)

/* 0x20 == NACK, 0xf == unknown command */
#define BUTTRESS_CSE2IUDATA0_IPC_NACK      0xf20
#define BUTTRESS_CSE2IUDATA0_IPC_NACK_MASK 0xffff

/* IS/PS freq control */
#define BUTTRESS_IS_FREQ_CTL_RATIO_MASK	0xffU
#define BUTTRESS_PS_FREQ_CTL_RATIO_MASK	0xffU

#define IPU7_IS_FREQ_MAX		450
#define IPU7_IS_FREQ_MIN		50
#define IPU7_PS_FREQ_MAX		750
#define BUTTRESS_PS_FREQ_RATIO_STEP		25U
/* valid for IPU8 */
#define BUTTRESS_IS_FREQ_RATIO_STEP		25U

/* IS: 400mhz, PS: 500mhz */
#define IPU7_IS_FREQ_CTL_DEFAULT_RATIO		0x1b
#define IPU7_PS_FREQ_CTL_DEFAULT_RATIO		0x14
/* IS: 400mhz, PS: 400mhz */
#define IPU8_IS_FREQ_CTL_DEFAULT_RATIO		0x10
#define IPU8_PS_FREQ_CTL_DEFAULT_RATIO		0x10

#define IPU_FREQ_CTL_CDYN		0x80
#define IPU_FREQ_CTL_RATIO_SHIFT	0x0
#define IPU_FREQ_CTL_CDYN_SHIFT		0x8

/* buttree power status */
#define IPU_BUTTRESS_PWR_STATE_IS_PWR_SHIFT	0
#define IPU_BUTTRESS_PWR_STATE_IS_PWR_MASK	\
	(0x3U << IPU_BUTTRESS_PWR_STATE_IS_PWR_SHIFT)

#define IPU_BUTTRESS_PWR_STATE_PS_PWR_SHIFT	4
#define IPU_BUTTRESS_PWR_STATE_PS_PWR_MASK	\
	(0x3U << IPU_BUTTRESS_PWR_STATE_PS_PWR_SHIFT)

#define IPU_BUTTRESS_PWR_STATE_DN_DONE		0x0
#define IPU_BUTTRESS_PWR_STATE_UP_PROCESS	0x1
#define IPU_BUTTRESS_PWR_STATE_DN_PROCESS	0x2
#define IPU_BUTTRESS_PWR_STATE_UP_DONE		0x3

#define BUTTRESS_PWR_STATE_IS_PWR_SHIFT	3
#define BUTTRESS_PWR_STATE_IS_PWR_MASK	(0x3 << 3)

#define BUTTRESS_PWR_STATE_PS_PWR_SHIFT	6
#define BUTTRESS_PWR_STATE_PS_PWR_MASK	(0x3 << 6)

#define PS_FSM_CG		BIT(3)

#define BUTTRESS_OVERRIDE_IS_CLK	BIT(1)
#define BUTTRESS_OVERRIDE_PS_CLK	BIT(2)
/* ps_pll only valid for ipu8 */
#define BUTTRESS_OWN_ACK_PS_PLL		BIT(8)
#define BUTTRESS_OWN_ACK_IS_CLK		BIT(9)
#define BUTTRESS_OWN_ACK_PS_CLK		BIT(10)

/* FW reset ctrl */
#define BUTTRESS_FW_RESET_CTL_START	BIT(0)
#define BUTTRESS_FW_RESET_CTL_DONE	BIT(1)

/* security */
#define BUTTRESS_SECURITY_CTL_FW_SECURE_MODE		BIT(16)
#define BUTTRESS_SECURITY_CTL_FW_SETUP_MASK		GENMASK(4, 0)

#define BUTTRESS_SECURITY_CTL_FW_SETUP_DONE		BIT(0)
#define BUTTRESS_SECURITY_CTL_AUTH_DONE			BIT(1)
#define BUTTRESS_SECURITY_CTL_AUTH_FAILED		BIT(3)

/* D2D */
#define BUTTRESS_D2D_PWR_EN			BIT(0)
#define BUTTRESS_D2D_PWR_ACK			BIT(4)

/* NDE */
#define NDE_VAL_MASK				GENMASK(9, 0)
#define NDE_SCALE_MASK				GENMASK(12, 10)
#define NDE_VALID_MASK				BIT(13)
#define NDE_RESVEC_MASK				GENMASK(19, 16)
#define NDE_IN_VBLANK_DIS_MASK			BIT(31)

#define BUTTRESS_NDE_VAL_ACTIVE			48
#define BUTTRESS_NDE_SCALE_ACTIVE		2
#define BUTTRESS_NDE_VALID_ACTIVE		1

#define BUTTRESS_NDE_VAL_DEFAULT		1023
#define BUTTRESS_NDE_SCALE_DEFAULT		2
#define BUTTRESS_NDE_VALID_DEFAULT		0

/* IS and PS UCX control */
#define UCX_CTL_RESET			BIT(0)
#define UCX_CTL_RUN			BIT(1)
#define UCX_CTL_WAKEUP			BIT(2)
#define UCX_CTL_SPARE			GENMASK(7, 3)
#define UCX_STS_PWR			GENMASK(17, 16)
#define UCX_STS_SLEEPING		BIT(18)

/* offset from PHY base */
#define PHY_CSI_CFG			0xc0
#define PHY_CSI_RCOMP_CONTROL		0xc8
#define PHY_CSI_BSCAN_EXCLUDE		0xd8

#define PHY_CPHY_DLL_OVRD(x)		(0x100 + 0x100 * (x))
#define PHY_DPHY_DLL_OVRD(x)		(0x14c + 0x100 * (x))
#define PHY_CPHY_RX_CONTROL1(x)		(0x110 + 0x100 * (x))
#define PHY_CPHY_RX_CONTROL2(x)		(0x114 + 0x100 * (x))
#define PHY_DPHY_CFG(x)			(0x148 + 0x100 * (x))
#define PHY_BB_AFE_CONFIG(x)		(0x174 + 0x100 * (x))

/* PB registers */
#define INTERRUPT_STATUS			0x0
#define BTRS_LOCAL_INTERRUPT_MASK		0x4
#define GLOBAL_INTERRUPT_MASK			0x8
#define HM_ATS					0xc
#define ATS_ERROR_LOG1				0x10
#define ATS_ERROR_LOG2				0x14
#define ATS_ERROR_CLEAR				0x18
#define CFI_0_ERROR_LOG				0x1c
#define CFI_0_ERROR_CLEAR			0x20
#define HASH_CONFIG				0x2c
#define TLBID_HASH_ENABLE_31_0			0x30
#define TLBID_HASH_ENABLE_63_32			0x34
#define TLBID_HASH_ENABLE_95_64			0x38
#define TLBID_HASH_ENABLE_127_96		0x3c
#define CFI_1_ERROR_LOGGING			0x40
#define CFI_1_ERROR_CLEAR			0x44
#define IMR_ERROR_LOGGING_LOW			0x48
#define IMR_ERROR_LOGGING_HIGH			0x4c
#define IMR_ERROR_CLEAR				0x50
#define PORT_ARBITRATION_WEIGHTS		0x54
#define IMR_ERROR_LOGGING_CFI_1_LOW		0x58
#define IMR_ERROR_LOGGING_CFI_1_HIGH		0x5c
#define IMR_ERROR_CLEAR_CFI_1			0x60
#define BAR2_MISC_CONFIG			0x64
#define RSP_ID_CONFIG_AXI2CFI_0			0x68
#define RSP_ID_CONFIG_AXI2CFI_1			0x6c
#define PB_DRIVER_PCODE_MAILBOX_STATUS		0x70
#define PB_DRIVER_PCODE_MAILBOX_INTERFACE	0x74
#define PORT_ARBITRATION_WEIGHTS_ATS		0x78

#endif /* IPU7_BUTTRESS_REGS_H */

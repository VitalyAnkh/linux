// SPDX-License-Identifier: GPL-2.0
// SPI driven IR LED device driver
//
// Copyright (c) 2016 Samsung Electronics Co., Ltd.
// Copyright (c) Andi Shyti <andi@etezian.org>

#include <linux/bits.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/math.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/property.h>
#include <linux/regulator/consumer.h>
#include <linux/spi/spi.h>
#include <linux/string.h>
#include <linux/types.h>

#include <media/rc-core.h>

#define IR_SPI_DRIVER_NAME		"ir-spi"

#define IR_SPI_DEFAULT_FREQUENCY	38000
#define IR_SPI_BITS_PER_PULSE		16

struct ir_spi_data {
	u32 freq;
	bool negated;

	u16 pulse;
	u16 space;

	struct rc_dev *rc;
	struct spi_device *spi;
	struct regulator *regulator;
};

static int ir_spi_tx(struct rc_dev *dev, unsigned int *buffer, unsigned int count)
{
	int i;
	int ret;
	unsigned int len = 0;
	struct ir_spi_data *idata = dev->priv;
	struct spi_transfer xfer;
	u16 *tx_buf;

	/* convert the pulse/space signal to raw binary signal */
	for (i = 0; i < count; i++) {
		buffer[i] = DIV_ROUND_CLOSEST_ULL((u64)buffer[i] * idata->freq,
						  1000000);
		len += buffer[i];
	}

	tx_buf = kmalloc_array(len, sizeof(*tx_buf), GFP_KERNEL);
	if (!tx_buf)
		return -ENOMEM;

	len = 0;
	for (i = 0; i < count; i++) {
		int j;
		u16 val;

		/*
		 * The first value in buffer is a pulse, so that 0, 2, 4, ...
		 * contain a pulse duration. On the contrary, 1, 3, 5, ...
		 * contain a space duration.
		 */
		val = (i % 2) ? idata->space : idata->pulse;
		for (j = 0; j < buffer[i]; j++)
			tx_buf[len++] = val;
	}

	memset(&xfer, 0, sizeof(xfer));

	xfer.speed_hz = idata->freq * IR_SPI_BITS_PER_PULSE;
	xfer.len = len * sizeof(*tx_buf);
	xfer.tx_buf = tx_buf;

	ret = regulator_enable(idata->regulator);
	if (ret)
		goto err_free_tx_buf;

	ret = spi_sync_transfer(idata->spi, &xfer, 1);
	if (ret)
		dev_err(&idata->spi->dev, "unable to deliver the signal\n");

	regulator_disable(idata->regulator);

err_free_tx_buf:

	kfree(tx_buf);

	return ret ? ret : count;
}

static int ir_spi_set_tx_carrier(struct rc_dev *dev, u32 carrier)
{
	struct ir_spi_data *idata = dev->priv;

	if (!carrier)
		return -EINVAL;

	if (carrier > idata->spi->max_speed_hz / IR_SPI_BITS_PER_PULSE)
		return -EINVAL;

	idata->freq = carrier;

	return 0;
}

static int ir_spi_set_duty_cycle(struct rc_dev *dev, u32 duty_cycle)
{
	struct ir_spi_data *idata = dev->priv;
	int bits = (duty_cycle * 15) / 100;

	idata->pulse = GENMASK(bits, 0);

	if (idata->negated) {
		idata->pulse = ~idata->pulse;
		idata->space = 0xffff;
	} else {
		idata->space = 0;
	}

	return 0;
}

static int ir_spi_probe(struct spi_device *spi)
{
	struct device *dev = &spi->dev;
	int ret;
	u8 dc;
	struct ir_spi_data *idata;

	idata = devm_kzalloc(dev, sizeof(*idata), GFP_KERNEL);
	if (!idata)
		return -ENOMEM;

	idata->regulator = devm_regulator_get(dev, "irda_regulator");
	if (IS_ERR(idata->regulator))
		return PTR_ERR(idata->regulator);

	idata->rc = devm_rc_allocate_device(&spi->dev, RC_DRIVER_IR_RAW_TX);
	if (!idata->rc)
		return -ENOMEM;

	idata->rc->tx_ir           = ir_spi_tx;
	idata->rc->s_tx_carrier    = ir_spi_set_tx_carrier;
	idata->rc->s_tx_duty_cycle = ir_spi_set_duty_cycle;
	idata->rc->device_name	   = "IR SPI";
	idata->rc->driver_name     = IR_SPI_DRIVER_NAME;
	idata->rc->priv            = idata;
	idata->spi                 = spi;

	idata->negated = device_property_read_bool(dev, "led-active-low");
	ret = device_property_read_u8(dev, "duty-cycle", &dc);
	if (ret)
		dc = 50;

	/*
	 * ir_spi_set_duty_cycle() cannot fail, it returns int
	 * to be compatible with the rc->s_tx_duty_cycle function.
	 */
	ir_spi_set_duty_cycle(idata->rc, dc);

	idata->freq = IR_SPI_DEFAULT_FREQUENCY;

	return devm_rc_register_device(dev, idata->rc);
}

static const struct of_device_id ir_spi_of_match[] = {
	{ .compatible = "ir-spi-led" },
	{}
};
MODULE_DEVICE_TABLE(of, ir_spi_of_match);

static const struct spi_device_id ir_spi_ids[] = {
	{ "ir-spi-led" },
	{}
};
MODULE_DEVICE_TABLE(spi, ir_spi_ids);

static struct spi_driver ir_spi_driver = {
	.probe = ir_spi_probe,
	.id_table = ir_spi_ids,
	.driver = {
		.name = IR_SPI_DRIVER_NAME,
		.of_match_table = ir_spi_of_match,
	},
};
module_spi_driver(ir_spi_driver);

MODULE_AUTHOR("Andi Shyti <andi@etezian.org>");
MODULE_DESCRIPTION("SPI IR LED");
MODULE_LICENSE("GPL v2");

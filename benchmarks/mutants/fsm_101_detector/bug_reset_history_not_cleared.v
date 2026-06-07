module top_module(input clk, input reset, input bit_in, output reg found);
    reg [2:0] hist = 3'b000;

    always @(posedge clk) begin
        if (reset) begin
            found <= 1'b0;
        end else begin
            hist <= {hist[1:0], bit_in};
            found <= ({hist[1:0], bit_in} == 3'b101);
        end
    end
endmodule
